from typing import Sequence, TypedDict
from typing_extensions import Annotated
from kubernetes import client, config
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
import subprocess
import getpass
import os
from datetime import datetime

if "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = getpass.getpass("Enter your Google AI API key: ")
    
config.load_kube_config()
api_instance = client.CoreV1Api()

@tool
def run_cli(cmd: str) -> str:
    """Ejecuta un comando de shell y devuelve stdout."""
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        return f"Error executing command: {e.output}"

class ClusterState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    events: list[dict]
    command_output: list[str]
    polished_events: dict
    report_content: str

def get_cluster_failing_events(state: ClusterState) -> ClusterState:
    events_response = api_instance.list_event_for_all_namespaces(
        field_selector="type=Warning",
        limit=100,
    )
    
    print(f"Total events fetched: {len(events_response.items)}")
    
    state['events'] = []
    state['polished_events'] = {}
    
    for event in events_response.items:
        print(f"Processing event: {event.metadata.name} - {event.reason} - {event.type}")
        if event.type == "Warning":
            event_dict = {
                'type': event.type,
                'reason': event.reason,
                'message': event.message,
                'count': event.count,
                'first_timestamp': str(event.first_timestamp) if event.first_timestamp else None,
                'last_timestamp': str(event.last_timestamp) if event.last_timestamp else None,
                'source': event.source.to_dict() if event.source else None,
                'event_time': str(event.event_time) if event.event_time else None,
                'namespace': event.metadata.namespace,
                'involved_object': event.involved_object.to_dict() if event.involved_object else None
            }
            
            state['events'].append(event_dict)
            state['polished_events'][event.metadata.name] = event_dict

        
    print(f"Found {len(state['events'])} failing events in the cluster.")
    return state

def llm_node(state: ClusterState) -> ClusterState:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0,
        max_output_tokens=1024,
    ).bind_tools([run_cli])
    
    if not state['events']:
        message = HumanMessage(content="No failing events found in the cluster. Everything looks good!")
        state['messages'] = [message]
        return state
    
    prompt = "Analyze the following Kubernetes events and provide insights:\n\n"
    for event in state['events']:
        prompt += f"Event: {event['reason']} - {event['message']} (Namespace: {event['namespace']})\n"
    prompt += "\nPlease summarize the issues and suggest potential solutions.\n"
    prompt += "If you need to run any kubectl commands to get more information, use the run_cli tool.\n"
    
    message = HumanMessage(content=prompt)
    response = llm.invoke([message])
    
    print("LLM Response:", response.content)
    
    # Add both the human message and AI response to state
    state['messages'] = [message, response]
    return state

def continue_analysis_node(state: ClusterState) -> ClusterState:
    """Continue the analysis after running tools."""
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0,
        max_output_tokens=1024,
    ).bind_tools([run_cli])
    
    # El LLM ve toda la conversación incluyendo los resultados de los comandos
    response = llm.invoke(state['messages'])
    
    print("LLM Continue Response:", response.content)
    new_messages = list(state['messages']) + [response]
    state['messages'] = new_messages
    
    return state

def should_continue_after_tools(state: ClusterState) -> str:
    """Determine if we should continue analysis or run more tools."""
    # Verificar si el último mensaje tiene tool calls
    if (state['messages'] and 
        isinstance(state['messages'][-1], AIMessage) and 
        hasattr(state['messages'][-1], 'tool_calls') and 
        state['messages'][-1].tool_calls):
        return "run_tools"
    
    # Límite de iteraciones para evitar bucles infinitos
    ai_messages = [msg for msg in state['messages'] if isinstance(msg, AIMessage)]
    if len(ai_messages) >= 5:  # Máximo 5 iteraciones
        return "end"
    
    return "end"

def should_continue(state: ClusterState) -> str:
    """Determine if we should continue with tool execution or end."""
    if not state['events']:
        return "end"
    
    # Check if the last message has tool calls
    if (state['messages'] and 
        isinstance(state['messages'][-1], AIMessage) and 
        hasattr(state['messages'][-1], 'tool_calls') and 
        state['messages'][-1].tool_calls):
        return "run_tools"
    
    return "end"


def run_tools_node(state: ClusterState) -> ClusterState:
    """Execute any tool calls from the LLM."""
    last_message = state['messages'][-1]
    
    if (isinstance(last_message, AIMessage) and 
        hasattr(last_message, 'tool_calls') and 
        last_message.tool_calls):
        
        # Ejecutar todas las tool calls
        tool_messages = []
        for tool_call in last_message.tool_calls:
            if tool_call['name'] == 'run_cli':
                cmd = tool_call['args']['cmd']
                result = run_cli.invoke({'cmd': cmd})
                print(f"Command: {cmd}")
                print(f"Result: {result}")
                
                # Crear un mensaje con el resultado del comando
                tool_message = ToolMessage(
                    content=f"Command: {cmd}\nOutput:\n{result}",
                    tool_call_id=tool_call['id']
                )
                tool_messages.append(tool_message)
                state['command_output'].append(result)
        
        # Agregar los mensajes de herramientas al estado
        # Crear una nueva lista con los mensajes existentes más los nuevos
        new_messages = list(state['messages']) + tool_messages
        state['messages'] = new_messages
    
    return state

def generate_report_node(state: ClusterState) -> ClusterState:
    """Generate a markdown report with the analysis results."""
    
    # Generar el contenido del reporte
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_content = f"""# Kubernetes Cluster Analysis Report

**Generated on:** {timestamp}

## Executive Summary

Total events analyzed: {len(state['events'])}
Warning events found: {len([e for e in state['events'] if e['type'] == 'Warning'])}

## Events Overview

"""
    
    # Agregar información de eventos
    if state['events']:
        report_content += "### Warning Events Found\n\n"
        for i, event in enumerate(state['events'], 1):
            report_content += f"""**{i}. {event['reason']}** (Namespace: `{event['namespace']}`)\n
- **Message:** {event['message']}
- **Count:** {event.get('count', 'N/A')}
- **Last Seen:** {event.get('last_timestamp', 'N/A')}
- **Involved Object:** {event.get('involved_object', {}).get('name', 'N/A')} ({event.get('involved_object', {}).get('kind', 'N/A')})

"""
    else:
        report_content += "### No Warning Events Found\n\nThe cluster appears to be healthy with no warning events detected.\n\n"
    
    # Agregar análisis del LLM
    report_content += "## AI Analysis\n\n"
    
    # Extraer mensajes de AI del estado
    ai_messages = [msg for msg in state['messages'] if isinstance(msg, AIMessage)]
    
    for i, ai_msg in enumerate(ai_messages, 1):
        report_content += f"### Analysis {i}\n\n"
        report_content += f"{ai_msg.content}\n\n"
    
    # Agregar comandos ejecutados
    if state['command_output']:
        report_content += "## Commands Executed\n\n"
        
        # Extraer comandos de los tool messages
        tool_messages = [msg for msg in state['messages'] if isinstance(msg, ToolMessage)]
        
        for i, tool_msg in enumerate(tool_messages, 1):
            # Extraer el comando del contenido del mensaje
            content = str(tool_msg.content)  # Asegurar que sea string
            lines = content.split('\n')
            if lines and lines[0].startswith('Command:'):
                command = lines[0].replace('Command: ', '')
                output = '\n'.join(lines[2:])  # Skip "Command:" and "Output:" lines
                
                report_content += f"### Command {i}\n\n"
                report_content += f"```bash\n{command}\n```\n\n"
                report_content += f"**Output:**\n```\n{output}\n```\n\n"
    
    # Agregar recomendaciones
    report_content += """## Recommendations

Based on the analysis above, consider the following actions:

1. **Review Critical Events:** Focus on events with high count or recent timestamps
2. **Check Resource Usage:** Monitor CPU, memory, and storage usage
3. **Verify Configurations:** Ensure deployments and services are properly configured
4. **Monitor Logs:** Check application logs for additional context
5. **Regular Health Checks:** Set up monitoring and alerting for cluster health

## Generated by Docktor
*Kubernetes Cluster Analysis Tool*
"""
    
    # Guardar el contenido en el estado
    state['report_content'] = report_content
    
    # Crear el nombre del archivo con timestamp
    filename = f"cluster-analysis-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"📄 Report saved to: {filename}")
    except Exception as e:
        print(f"❌ Error saving report: {e}")
    
    return state

# Inicialización del estado
initial_state = {
    'messages': [],
    'events': [],
    'command_output': [],
    'polished_events': {},
    'report_content': ''
}

graph = StateGraph(ClusterState)
graph.add_node("get_events", get_cluster_failing_events)
graph.add_node("analyze", llm_node)
graph.add_node("run_tools", run_tools_node)
graph.add_node("continue_analysis", continue_analysis_node)
graph.add_node("generate_report", generate_report_node)

graph.set_entry_point("get_events")
graph.add_edge("get_events", "analyze")

graph.add_conditional_edges(
    "analyze",
    should_continue,
    {
        "run_tools": "run_tools",
        "end": "generate_report",
    },
)

# Después de ejecutar tools, continuar con el análisis
graph.add_edge("run_tools", "continue_analysis")

# Desde continue_analysis, verificar si necesita más tools o generar reporte
graph.add_conditional_edges(
    "continue_analysis",
    should_continue_after_tools,
    {
        "run_tools": "run_tools",
        "end": "generate_report",
    },
)

# Generar reporte al final
graph.add_edge("generate_report", "__end__")

compiled = graph.compile()
result = compiled.invoke(initial_state)
print("\nExecution completed!")
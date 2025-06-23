# Docktor

**Stop debugging Kubernetes clusters manually.**

Docktor scans your cluster for problems, runs the diagnostic commands you'd normally run by hand, and gives you a comprehensive report. It's like having an experienced DevOps engineer look at your cluster issues while you grab coffee.

## What it does

- Finds Warning events across your entire cluster
- Investigates each problem by running kubectl commands
- Produces a readable Markdown report with findings
- Cuts debugging time from hours to minutes

## Getting Started

```bash
# Install what you need
pip install -r requirements.txt

# Point it at your cluster and run
python main.py
```

You'll get a timestamped report with everything Docktor found.

## What You Need

- Python 3.12 or newer
- kubectl configured for your cluster
- Google AI API key (we'll ask for it on first run)

## Sample Run

```
Total events fetched: 32
Found 32 failing events in the cluster.
📄 Report saved to: cluster-analysis-20250622-223001.md
```

Your report will include:
- Summary of what's broken and how badly
- Every warning event, organized by namespace  
- Analysis of what's causing the problems
- All the diagnostic commands we ran (with their output)
- Specific steps to fix the issues

## Problems We Catch

- Pods stuck in crash loops
- Out of memory kills and resource limits hit
- Network issues and DNS failures  
- Storage problems and volume mount errors
- Bad configurations and missing images
- Pretty much anything that shows up as a Warning event

## Sample Report Structure

```markdown
# Kubernetes Cluster Analysis Report

## Executive Summary
Total events analyzed: 32
Warning events found: 32

## Events Overview
### Warning Events Found
**1. BackOff** (Namespace: chaos-experiments)
- Message: Back-off restarting failed container...
- Count: 14
- Last Seen: 2025-06-22 22:30:01

## AI Analysis
### Analysis 1
The events indicate widespread problems across multiple namespaces...

## Commands Executed
### Command 1
```bash
kubectl get nodes -o wide
```

## Recommendations
1. Review Critical Events
2. Check Resource Usage
3. Verify Configurations
```

## Setting Up Your API Key

```bash
export GOOGLE_API_KEY="your-key-here"
```

Or just run the tool - it'll ask you for the key if you haven't set it.

## Want to Test It?

We've included a script that spins up a minikube cluster with intentionally broken stuff:

```bash
cd cluster-diy
bash setup.sh
```

Run Docktor against this cluster and you'll see it catch all sorts of problems.

## Why We Built This

We got tired of doing the same debugging dance every time something broke in Kubernetes:
1. Check events
2. Describe the failing pods  
3. Look at logs
4. Run a bunch of kubectl commands
5. Try to piece together what's actually wrong

Docktor does steps 1-4 automatically and gives you step 5 on a silver platter.

Built by people who debug Kubernetes clusters for a living.

## License

MIT

## Contributing

Found a bug? Open an issue.
Want to add a feature? Submit a pull request.
Have ideas? We'd love to hear them.

Just keep it simple - that's the whole point of this tool.

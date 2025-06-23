#!/bin/bash

set -e  

echo "🚀 Setting up Kubernetes cluster for Docktor testing..."

echo "📦 Starting minikube..."
minikube start --driver=docker --cpus 2 --memory 4096

echo "⏳ Waiting for cluster to be ready..."
kubectl wait --for=condition=Ready nodes --all --timeout=300s

echo "🧹 Cleaning up existing installations..."
kubectl delete namespace chaos-experiments --ignore-not-found=true
kubectl delete namespace chaos-mesh --ignore-not-found=true

echo "📚 Adding Chaos Mesh helm repository..."
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update

echo "🔧 Installing Chaos Mesh..."
kubectl create namespace chaos-mesh
helm install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace=chaos-mesh \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock \
  --wait

echo "⏳ Waiting for Chaos Mesh to be ready..."
kubectl wait --for=condition=Ready pods --all -n chaos-mesh --timeout=300s

echo "🎯 Creating chaos experiments namespace..."
kubectl create namespace chaos-experiments

echo "🧪 Creating test pods..."
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: crashloop-test
  namespace: chaos-experiments
spec:
  replicas: 1
  selector:
    matchLabels:
      app: crashloop-test
  template:
    metadata:
      labels:
        app: crashloop-test
    spec:
      containers:
      - name: boom
        image: busybox
        command: ["/bin/sh", "-c"]
        args: ["echo '💥 crash'; exit 1"]
---
apiVersion: batch/v1
kind: Job
metadata:
  name: oomkill-test
  namespace: chaos-experiments
spec:
  template:
    spec:
      containers:
      - name: memory-hog
        image: polinux/stress
        command: ["/usr/bin/stress"]
        args: ["--vm", "1", "--vm-bytes", "512M", "--timeout", "30s"]
        resources:
          limits:
            memory: "256Mi"
          requests:
            memory: "128Mi"
      restartPolicy: Never
  backoffLimit: 2
EOF

echo "✅ Setup completed successfully!"
echo ""
echo "🔍 Cluster status:"
kubectl get nodes
echo ""
kubectl get pods -A
echo ""
echo "🎉 Ready to test Docktor!"
echo "Run: python main.py"

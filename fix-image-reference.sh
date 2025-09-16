#!/bin/bash

# Fix Image Reference issues for IPAM4Lab
# Usage: ./fix-image-reference.sh [namespace]

set -e

NAMESPACE=${1:-ipam4lab}

echo "🔧 Fixing Image Reference issues for IPAM4Lab"
echo "📁 Namespace: $NAMESPACE"

# Check if oc is available
if ! command -v oc &> /dev/null; then
    echo "❌ OpenShift CLI (oc) is not installed or not in PATH"
    exit 1
fi

# Check if logged into OpenShift
if ! oc whoami &> /dev/null; then
    echo "❌ Not logged into OpenShift. Please run 'oc login' first."
    exit 1
fi

# Switch to the namespace
echo "📦 Switching to namespace: $NAMESPACE"
oc project $NAMESPACE

echo "🔍 Checking current image status..."
echo "ImageStreams:"
oc get imagestream

echo ""
echo "Builds:"
oc get builds

echo ""
echo "Current deployment image reference:"
oc get deployment ipam4lab -o jsonpath='{.spec.template.spec.containers[0].image}'
echo ""

# Get the internal registry URL for the built image
INTERNAL_REGISTRY=$(oc get imagestream ipam4lab -o jsonpath='{.status.dockerImageRepository}')

if [ -z "$INTERNAL_REGISTRY" ]; then
    echo "❌ No imagestream found. Build may have failed."
    echo "   Check build logs: oc logs build/ipam4lab-build-1"
    exit 1
fi

echo "✅ Found internal registry image: $INTERNAL_REGISTRY:latest"

echo "🗑️  Deleting current deployment..."
oc delete deployment ipam4lab --ignore-not-found=true

echo "⏳ Waiting for pods to terminate..."
sleep 5

echo "🔧 Creating deployment with correct image reference..."
cat <<EOF | oc apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ipam4lab
  labels:
    app: ipam4lab
    version: v1
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ipam4lab
  template:
    metadata:
      labels:
        app: ipam4lab
        version: v1
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
      - name: ipam4lab
        image: $INTERNAL_REGISTRY:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8080
          protocol: TCP
        env:
        - name: PUBLIC_NETWORK_CIDR
          valueFrom:
            configMapKeyRef:
              name: ipam4lab-config
              key: public_network_cidr
        - name: DATABASE_PATH
          value: "/data/ipam.db"
        - name: PORT
          value: "8080"
        - name: PYTHONUNBUFFERED
          value: "1"
        volumeMounts:
        - name: data
          mountPath: /data
        resources:
          limits:
            cpu: 500m
            memory: 512Mi
          requests:
            cpu: 200m
            memory: 256Mi
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: ipam4lab-data
EOF

echo "⏳ Waiting for deployment to be ready..."
oc rollout status deployment/ipam4lab --timeout=300s

echo "📊 Checking pod status..."
oc get pods -l app=ipam4lab

echo ""
echo "🔍 Checking pod events..."
POD_NAME=$(oc get pods -l app=ipam4lab -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ ! -z "$POD_NAME" ]; then
    echo "Pod: $POD_NAME"
    oc describe pod $POD_NAME | grep -A 5 "Events:" || echo "No events found"
fi

echo ""
echo "✅ Image reference issue fixed!"
echo ""
echo "🧪 Test the service:"
ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ ! -z "$ROUTE_URL" ]; then
    echo "curl -k https://$ROUTE_URL/health"
else
    echo "Route not found - check route creation"
fi

#!/bin/bash

# Fix Security Context Constraint issues for IPAM4Lab
# Usage: ./fix-security-context.sh [namespace]

set -e

NAMESPACE=${1:-ipam4lab}

echo "🔧 Fixing Security Context Constraint issues for IPAM4Lab"
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

echo "🗑️  Deleting current deployment..."
oc delete deployment ipam4lab --ignore-not-found=true

echo "⏳ Waiting for pods to terminate..."
sleep 5

echo "🔧 Creating OpenShift-compatible deployment..."
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
        image: ipam4lab:latest
        imagePullPolicy: Always
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
          initialDelaySeconds: 5
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
echo "✅ Security context issue fixed!"
echo ""
echo "🧪 Test the service:"
ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ ! -z "$ROUTE_URL" ]; then
    echo "curl -k https://$ROUTE_URL/health"
else
    echo "Route not found - check route creation"
fi

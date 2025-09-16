#!/bin/bash

# IPAM4Lab Simple OpenShift Deployment Script (without BuildConfig)
# Usage: ./deploy-simple.sh [namespace] [public_network_cidr] [image]

set -e

NAMESPACE=${1:-ipam4lab}
NETWORK_CIDR=${2:-192.168.0.0/16}
IMAGE=${3:-quay.io/python/python:3.11}

echo "🚀 Simple IPAM4Lab Deployment to OpenShift"
echo "📁 Namespace: $NAMESPACE"
echo "🌐 Network CIDR: $NETWORK_CIDR"
echo "🐳 Base Image: $IMAGE"

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

# Create namespace if it doesn't exist
echo "📦 Creating namespace: $NAMESPACE"
oc new-project $NAMESPACE 2>/dev/null || oc project $NAMESPACE

# Create ConfigMap
echo "⚙️  Creating ConfigMap..."
oc create configmap ipam4lab-config \
  --from-literal=public_network_cidr="$NETWORK_CIDR" \
  --dry-run=client -o yaml | oc apply -f -

# Create PVC
echo "💾 Creating PersistentVolumeClaim..."
cat <<EOF | oc apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ipam4lab-data
  labels:
    app: ipam4lab
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
EOF

# Create the application code as a ConfigMap
echo "📝 Creating application code ConfigMap..."
oc create configmap ipam4lab-app \
  --from-file=app.py \
  --from-file=requirements.txt \
  --dry-run=client -o yaml | oc apply -f -

# Create a simpler deployment that installs the app at runtime
echo "🔧 Creating Deployment..."
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
      initContainers:
      - name: install-deps
        image: $IMAGE
        command: ['sh', '-c']
        args:
        - |
          cd /app
          pip install --user -r requirements.txt
          cp -r /root/.local /shared/
        volumeMounts:
        - name: app-code
          mountPath: /app
        - name: shared
          mountPath: /shared
        securityContext:
          runAsUser: 0  # Need root for pip install
      containers:
      - name: ipam4lab
        image: $IMAGE
        command: ['sh', '-c']
        args:
        - |
          export PYTHONPATH=/shared/.local/lib/python3.11/site-packages:\$PYTHONPATH
          export PATH=/shared/.local/bin:\$PATH
          cd /app
          python app.py
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
        - name: app-code
          mountPath: /app
        - name: shared
          mountPath: /shared
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
        securityContext:
          runAsNonRoot: true
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: ipam4lab-data
      - name: app-code
        configMap:
          name: ipam4lab-app
      - name: shared
        emptyDir: {}
EOF

# Create Service
echo "🔧 Creating Service..."
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Service
metadata:
  name: ipam4lab-service
  labels:
    app: ipam4lab
spec:
  selector:
    app: ipam4lab
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
    name: http
  type: ClusterIP
EOF

# Create Route
echo "🔧 Creating Route..."
cat <<EOF | oc apply -f -
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: ipam4lab-route
  labels:
    app: ipam4lab
spec:
  to:
    kind: Service
    name: ipam4lab-service
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
EOF

# Wait for deployment to be ready
echo "⏳ Waiting for deployment to be ready..."
oc rollout status deployment/ipam4lab --timeout=300s

# Get the route URL
ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "Route not found")

echo ""
echo "✅ IPAM4Lab deployed successfully!"
echo ""
echo "📊 Deployment Status:"
oc get pods -l app=ipam4lab
echo ""
echo "🌐 Service URL: https://$ROUTE_URL"
echo ""
echo "🧪 Test the service:"
echo "curl -k https://$ROUTE_URL/health"
echo ""
echo "📖 Example allocation:"
echo "curl -k -X POST https://$ROUTE_URL/allocate \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"lab_uid\": \"test-lab-001\"}'"
echo ""
echo "🚀 Simple deployment complete!"

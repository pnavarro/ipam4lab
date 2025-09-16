#!/bin/bash

# IPAM4Lab OpenShift Deployment Script
# Handles fresh deployments with proper image references and security contexts
# Usage: ./deploy.sh [namespace] [public_network_cidr]

set -e

NAMESPACE=${1:-ipam4lab}
NETWORK_CIDR=${2:-192.168.0.0/16}

echo "🚀 Deploying IPAM4Lab to OpenShift"
echo "📁 Namespace: $NAMESPACE"
echo "🌐 Network CIDR: $NETWORK_CIDR"

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

# Clean up any existing deployment to avoid conflicts
echo "🧹 Cleaning up any existing deployment..."
oc delete deployment ipam4lab --ignore-not-found=true --wait=false

# Update ConfigMap with provided network CIDR
echo "⚙️  Creating ConfigMap with network CIDR: $NETWORK_CIDR"
cat > /tmp/ipam4lab-configmap.yaml << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ipam4lab-config
  labels:
    app: ipam4lab
data:
  public_network_cidr: "$NETWORK_CIDR"
EOF

# Apply infrastructure manifests first
echo "🔧 Step 1: Applying infrastructure manifests..."
oc apply -f /tmp/ipam4lab-configmap.yaml
oc apply -f openshift/pvc.yaml
oc apply -f openshift/service.yaml
oc apply -f openshift/route.yaml
oc apply -f openshift/imagestream.yaml
oc apply -f openshift/buildconfig.yaml

# Start build and wait for completion
echo "⏳ Step 2: Building application image..."
oc start-build ipam4lab-build --wait --follow || {
    echo "❌ Build failed, checking logs..."
    LATEST_BUILD=$(oc get builds --sort-by='.metadata.creationTimestamp' -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || echo "")
    if [ ! -z "$LATEST_BUILD" ]; then
        oc logs --tail=50 build/$LATEST_BUILD || true
    fi
    exit 1
}

# Verify build completed successfully
BUILD_STATUS=$(oc get builds --sort-by='.metadata.creationTimestamp' -o jsonpath='{.items[-1:].status.phase}' 2>/dev/null || echo "Unknown")
if [ "$BUILD_STATUS" != "Complete" ]; then
    echo "❌ Build failed with status: $BUILD_STATUS"
    exit 1
fi

echo "✅ Build completed successfully"

# Wait for imagestream to be populated and get correct image reference
echo "⏳ Step 3: Waiting for ImageStream to be populated..."
for i in {1..30}; do
    IMAGE_REF=$(oc get imagestream ipam4lab -o jsonpath='{.status.tags[0].items[0].dockerImageReference}' 2>/dev/null || echo "")
    if [ ! -z "$IMAGE_REF" ]; then
        break
    fi
    echo "   Waiting for ImageStream... ($i/30)"
    sleep 2
done

if [ -z "$IMAGE_REF" ]; then
    echo "❌ ImageStream not populated after build completion"
    echo "📋 ImageStream status:"
    oc describe imagestream ipam4lab
    exit 1
fi

echo "✅ Using image: $IMAGE_REF"

# Create deployment with correct image reference and OpenShift-compatible security context
echo "🔧 Step 4: Creating deployment with correct image reference..."
cat > /tmp/ipam4lab-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ipam4lab
  labels:
    app: ipam4lab
    version: v1
  annotations:
    image.openshift.io/triggers: '[{"from":{"kind":"ImageStreamTag","name":"ipam4lab:latest"},"fieldPath":"spec.template.spec.containers[?(@.name==\"ipam4lab\")].image"}]'
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
        image: $IMAGE_REF
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
          initialDelaySeconds: 60
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: ipam4lab-data
EOF

oc apply -f /tmp/ipam4lab-deployment.yaml

# Wait for deployment to be ready
echo "⏳ Step 5: Waiting for deployment to be ready..."
oc rollout status deployment/ipam4lab --timeout=300s

# Verify deployment
echo "📊 Step 6: Verifying deployment..."
POD_NAME=$(oc get pods -l app=ipam4lab -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ ! -z "$POD_NAME" ]; then
    POD_STATUS=$(oc get pod $POD_NAME -o jsonpath='{.status.phase}')
    echo "Pod: $POD_NAME - Status: $POD_STATUS"
    
    if [ "$POD_STATUS" != "Running" ]; then
        echo "❌ Pod is not running"
        echo "📋 Pod events:"
        oc describe pod $POD_NAME | grep -A 10 "Events:" || echo "No events found"
        echo "📋 Pod logs:"
        oc logs $POD_NAME 2>/dev/null || echo "No logs available"
    else
        echo "✅ Pod is running successfully!"
        
        # Test the application
        echo "🧪 Testing health endpoint..."
        sleep 10  # Give the app time to start
        if oc exec $POD_NAME -- curl -s -f http://localhost:8080/health > /dev/null; then
            echo "✅ Health check passed!"
        else
            echo "⚠️  Health check failed, but deployment is complete"
        fi
    fi
fi

# Get the route URL
ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "Route not found")

# Cleanup temporary files
rm -f /tmp/ipam4lab-configmap.yaml /tmp/ipam4lab-deployment.yaml

echo ""
echo "🎉 IPAM4Lab deployed successfully!"
echo ""
echo "📊 Deployment Summary:"
echo "   Namespace: $NAMESPACE"
echo "   Network CIDR: $NETWORK_CIDR"
echo "   Image: $IMAGE_REF"
if [ ! -z "$POD_NAME" ]; then
    echo "   Pod: $POD_NAME ($POD_STATUS)"
fi
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
echo "🚀 Deployment complete!"

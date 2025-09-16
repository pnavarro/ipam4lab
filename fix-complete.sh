#!/bin/bash

# Complete fix for IPAM4Lab deployment issues
# Usage: ./fix-complete.sh [namespace]

set -e

NAMESPACE=${1:-ipam4lab}

echo "🔧 Complete fix for IPAM4Lab deployment issues"
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

echo "🔍 Checking build and image status..."
echo "Builds:"
oc get builds

echo ""
echo "ImageStreams:"
oc get imagestream ipam4lab -o wide 2>/dev/null || echo "No imagestream found"

# Wait for build to complete if it's still running
BUILD_STATUS=$(oc get builds -o jsonpath='{.items[-1:].status.phase}' 2>/dev/null || echo "Unknown")
if [ "$BUILD_STATUS" = "Running" ]; then
    echo "⏳ Build is still running, waiting for completion..."
    oc logs -f build/ipam4lab-build-1 || true
fi

# Check if we have a successful build
LATEST_BUILD=$(oc get builds --sort-by='.metadata.creationTimestamp' -o jsonpath='{.items[-1:].metadata.name}' 2>/dev/null || echo "")
if [ ! -z "$LATEST_BUILD" ]; then
    BUILD_STATUS=$(oc get build $LATEST_BUILD -o jsonpath='{.status.phase}')
    echo "Latest build: $LATEST_BUILD - Status: $BUILD_STATUS"
    
    if [ "$BUILD_STATUS" != "Complete" ]; then
        echo "❌ Build not completed successfully. Status: $BUILD_STATUS"
        echo "Check build logs:"
        oc logs build/$LATEST_BUILD | tail -20
        exit 1
    fi
else
    echo "❌ No builds found"
    exit 1
fi

# Get the correct image reference
IMAGE_STREAM_IMAGE=$(oc get imagestream ipam4lab -o jsonpath='{.status.tags[0].items[0].dockerImageReference}' 2>/dev/null || echo "")
if [ -z "$IMAGE_STREAM_IMAGE" ]; then
    echo "❌ No image found in imagestream"
    exit 1
fi

echo "✅ Using image: $IMAGE_STREAM_IMAGE"

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
        image: $IMAGE_STREAM_IMAGE
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

echo "⏳ Waiting for deployment to be ready..."
oc rollout status deployment/ipam4lab --timeout=300s

echo "📊 Final status check..."
echo "Pods:"
oc get pods -l app=ipam4lab

echo ""
echo "Deployment:"
oc get deployment ipam4lab

echo ""
echo "Service & Route:"
oc get service ipam4lab-service
oc get route ipam4lab-route

echo ""
POD_NAME=$(oc get pods -l app=ipam4lab -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ ! -z "$POD_NAME" ]; then
    POD_STATUS=$(oc get pod $POD_NAME -o jsonpath='{.status.phase}')
    echo "Pod $POD_NAME status: $POD_STATUS"
    
    if [ "$POD_STATUS" != "Running" ]; then
        echo "🔍 Pod is not running, checking events..."
        oc describe pod $POD_NAME | grep -A 10 "Events:" || echo "No events found"
        
        echo ""
        echo "🔍 Pod logs:"
        oc logs $POD_NAME 2>/dev/null || echo "No logs available"
    else
        echo "✅ Pod is running successfully!"
        
        # Test the health endpoint
        echo "🧪 Testing health endpoint..."
        oc exec $POD_NAME -- curl -s http://localhost:8080/health || echo "Health check failed"
    fi
fi

echo ""
echo "🌐 External access:"
ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
if [ ! -z "$ROUTE_URL" ]; then
    echo "Service URL: https://$ROUTE_URL"
    echo ""
    echo "🧪 Test commands:"
    echo "curl -k https://$ROUTE_URL/health"
    echo "curl -k -X POST https://$ROUTE_URL/allocate -H 'Content-Type: application/json' -d '{\"lab_uid\": \"test-001\"}'"
else
    echo "❌ Route not found"
fi

echo ""
echo "🎉 Deployment fix complete!"

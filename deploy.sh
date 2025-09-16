#!/bin/bash

# IPAM4Lab OpenShift Deployment Script
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

# Update ConfigMap with provided network CIDR
echo "⚙️  Updating ConfigMap with network CIDR: $NETWORK_CIDR"
cat > openshift/configmap.yaml << EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: ipam4lab-config
  labels:
    app: ipam4lab
data:
  public_network_cidr: "$NETWORK_CIDR"
EOF

# Apply all manifests
echo "🔧 Applying OpenShift manifests..."
oc apply -f openshift/

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
echo "curl https://$ROUTE_URL/health"
echo ""
echo "📖 Example allocation:"
echo "curl -X POST https://$ROUTE_URL/allocate \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"lab_uid\": \"test-lab-001\"}'"
echo ""
echo "🚀 Deployment complete!"

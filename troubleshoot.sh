#!/bin/bash

# IPAM4Lab OpenShift Troubleshooting Script
# Usage: ./troubleshoot.sh [namespace]

set -e

NAMESPACE=${1:-ipam4lab}

echo "🔍 IPAM4Lab OpenShift Troubleshooting"
echo "📁 Namespace: $NAMESPACE"
echo "=" * 60

# Check if oc is available
if ! command -v oc &> /dev/null; then
    echo "❌ OpenShift CLI (oc) is not installed or not in PATH"
    echo "   Install it from: https://mirror.openshift.com/pub/openshift-v4/clients/ocp/"
    exit 1
fi

# Check if logged into OpenShift
if ! oc whoami &> /dev/null; then
    echo "❌ Not logged into OpenShift. Please run 'oc login' first."
    echo "   Example: oc login --token=your-token --server=https://api.cluster.com:6443"
    exit 1
fi

echo "✅ OpenShift CLI available and logged in"
echo "👤 Current user: $(oc whoami)"
echo "🌐 Current server: $(oc whoami --show-server)"
echo ""

# Check if namespace exists
if ! oc get namespace $NAMESPACE &> /dev/null; then
    echo "❌ Namespace '$NAMESPACE' does not exist"
    echo "   Create it with: oc new-project $NAMESPACE"
    exit 1
fi

# Switch to the namespace
echo "📦 Switching to namespace: $NAMESPACE"
oc project $NAMESPACE
echo ""

# Check current resources
echo "📊 Current Resources Status:"
echo "=" * 40

echo "🔧 Deployments:"
if oc get deployments -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get deployments -l app=ipam4lab
    echo ""
    echo "Deployment Details:"
    oc describe deployment ipam4lab 2>/dev/null | head -30
else
    echo "  No deployments found with label app=ipam4lab"
fi
echo ""

echo "🔧 Pods:"
if oc get pods -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get pods -l app=ipam4lab -o wide
    echo ""
    
    # Check pod logs if any pods exist
    POD_NAME=$(oc get pods -l app=ipam4lab -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    if [ ! -z "$POD_NAME" ]; then
        echo "📝 Recent logs from pod $POD_NAME:"
        echo "---"
        oc logs $POD_NAME --tail=20 2>/dev/null || echo "No logs available"
        echo "---"
        echo ""
        
        echo "🔍 Pod events:"
        oc describe pod $POD_NAME | grep -A 10 "Events:" || echo "No events found"
    fi
else
    echo "  No pods found with label app=ipam4lab"
fi
echo ""

echo "🔧 Services:"
if oc get services -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get services -l app=ipam4lab
else
    echo "  No services found with label app=ipam4lab"
fi
echo ""

echo "🔧 Routes:"
if oc get routes -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get routes -l app=ipam4lab
    ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}' 2>/dev/null || echo "")
    if [ ! -z "$ROUTE_URL" ]; then
        echo "🌐 Route URL: https://$ROUTE_URL"
    fi
else
    echo "  No routes found with label app=ipam4lab"
fi
echo ""

echo "🔧 ConfigMaps:"
if oc get configmaps -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get configmaps -l app=ipam4lab
    echo ""
    echo "ConfigMap content:"
    oc get configmap ipam4lab-config -o yaml 2>/dev/null | grep -A 10 "data:" || echo "No data found"
else
    echo "  No configmaps found with label app=ipam4lab"
fi
echo ""

echo "🔧 PersistentVolumeClaims:"
if oc get pvc -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get pvc -l app=ipam4lab
else
    echo "  No PVCs found with label app=ipam4lab"
fi
echo ""

echo "🔧 BuildConfigs:"
if oc get buildconfigs -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get buildconfigs -l app=ipam4lab
    echo ""
    echo "Build status:"
    oc get builds -l app=ipam4lab 2>/dev/null || echo "No builds found"
else
    echo "  No buildconfigs found with label app=ipam4lab"
fi
echo ""

echo "🔧 ImageStreams:"
if oc get imagestreams -l app=ipam4lab --no-headers 2>/dev/null | grep -q .; then
    oc get imagestreams -l app=ipam4lab
    echo ""
    echo "ImageStream tags:"
    oc get imagestream ipam4lab -o jsonpath='{.status.tags[*].tag}' 2>/dev/null || echo "No tags found"
else
    echo "  No imagestreams found with label app=ipam4lab"
fi
echo ""

# Check events
echo "📅 Recent Namespace Events:"
echo "=" * 40
oc get events --sort-by='.lastTimestamp' | tail -10
echo ""

# Check node resources
echo "🖥️  Cluster Node Status:"
echo "=" * 40
oc get nodes
echo ""

# Storage classes
echo "💾 Available Storage Classes:"
echo "=" * 40
oc get storageclass
echo ""

# Check if we can create basic resources
echo "🧪 Basic Permissions Test:"
echo "=" * 40
echo "Testing if we can create a basic pod..."
cat > /tmp/test-pod.yaml << EOF
apiVersion: v1
kind: Pod
metadata:
  name: test-permissions
  labels:
    test: permissions
spec:
  containers:
  - name: test
    image: registry.redhat.io/ubi8/ubi-minimal:latest
    command: ['sleep', '30']
  restartPolicy: Never
EOF

if oc apply -f /tmp/test-pod.yaml --dry-run=client &>/dev/null; then
    echo "✅ Basic pod creation permissions OK"
else
    echo "❌ Cannot create basic pods - permission issues"
fi

# Clean up test file
rm -f /tmp/test-pod.yaml

echo ""
echo "🔍 Common Issues Checklist:"
echo "=" * 40
echo "1. ❓ Image pull issues:"
echo "   - Check if buildconfig completed successfully"
echo "   - Verify imagestream has tags"
echo "   - Look for ImagePullBackOff in pod status"
echo ""
echo "2. ❓ Storage issues:"
echo "   - Check if PVC is bound"
echo "   - Verify storage class exists and is default"
echo "   - Look for volume mount errors in pod events"
echo ""
echo "3. ❓ Permission issues:"
echo "   - Verify user has admin rights in namespace"
echo "   - Check for SecurityContextConstraints errors"
echo "   - Look for forbidden errors in events"
echo ""
echo "4. ❓ Network issues:"
echo "   - Verify route is created and accessible"
echo "   - Check if service endpoints are ready"
echo "   - Test internal connectivity"
echo ""
echo "🔧 Next Steps:"
echo "=" * 40
echo "1. If no resources exist, run: ./deploy.sh $NAMESPACE"
echo "2. If build is failing, check: oc logs bc/ipam4lab-build"
echo "3. If pods are failing, check: oc describe pod <pod-name>"
echo "4. If route is not working, test: curl -k https://<route-url>/health"
echo ""
echo "💡 For more help, run specific commands shown above"

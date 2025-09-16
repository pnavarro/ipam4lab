#!/bin/bash

# IPAM4Lab OpenShift Undeployment Script
# Usage: ./undeploy.sh [namespace] [--keep-namespace]

set -e

NAMESPACE=${1:-ipam4lab}
KEEP_NAMESPACE=false

# Check for --keep-namespace flag
for arg in "$@"; do
    case $arg in
        --keep-namespace)
            KEEP_NAMESPACE=true
            shift
            ;;
    esac
done

echo "🗑️  Undeploying IPAM4Lab from OpenShift"
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

# Check if namespace exists
if ! oc get namespace $NAMESPACE &> /dev/null; then
    echo "❌ Namespace '$NAMESPACE' does not exist"
    exit 1
fi

# Switch to the namespace
echo "📦 Switching to namespace: $NAMESPACE"
oc project $NAMESPACE

# Get current resources before deletion
echo "📊 Current IPAM4Lab resources:"
echo "Deployments:"
oc get deployments -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo "Services:"
oc get services -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo "Routes:"
oc get routes -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo "ConfigMaps:"
oc get configmaps -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo "PVCs:"
oc get pvc -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo "BuildConfigs:"
oc get buildconfigs -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo "ImageStreams:"
oc get imagestreams -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"

echo ""
read -p "⚠️  Are you sure you want to delete all IPAM4Lab resources? [y/N]: " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Undeployment cancelled"
    exit 0
fi

echo ""
echo "🧹 Deleting IPAM4Lab resources..."

# Delete resources in order (most dependent first)
echo "🔧 Deleting Route..."
oc delete route ipam4lab-route --ignore-not-found=true

echo "🔧 Deleting Service..."
oc delete service ipam4lab-service --ignore-not-found=true

echo "🔧 Deleting Deployment..."
oc delete deployment ipam4lab --ignore-not-found=true

echo "🔧 Deleting ConfigMap..."
oc delete configmap ipam4lab-config --ignore-not-found=true

echo "🔧 Deleting BuildConfig..."
oc delete buildconfig ipam4lab-build --ignore-not-found=true

echo "🔧 Deleting ImageStream..."
oc delete imagestream ipam4lab --ignore-not-found=true

# Ask about PVC since it contains data
echo ""
read -p "⚠️  Delete PersistentVolumeClaim (this will delete all allocation data)? [y/N]: " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔧 Deleting PersistentVolumeClaim..."
    oc delete pvc ipam4lab-data --ignore-not-found=true
    echo "💾 Database data has been permanently deleted"
else
    echo "💾 PersistentVolumeClaim kept (data preserved)"
fi

# Delete any remaining resources with the app label
echo ""
echo "🔧 Cleaning up any remaining labeled resources..."
oc delete all -l app=ipam4lab --ignore-not-found=true

# Option to delete namespace
if [ "$KEEP_NAMESPACE" = false ]; then
    echo ""
    read -p "🗑️  Delete the entire namespace '$NAMESPACE'? [y/N]: " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔧 Deleting namespace: $NAMESPACE"
        oc delete namespace $NAMESPACE
        echo "📁 Namespace '$NAMESPACE' deleted"
    else
        echo "📁 Namespace '$NAMESPACE' kept"
    fi
else
    echo "📁 Namespace '$NAMESPACE' kept (--keep-namespace flag used)"
fi

echo ""
echo "✅ IPAM4Lab undeployment completed!"
echo ""
echo "📊 Final status:"
echo "Remaining deployments with app=ipam4lab:"
oc get deployments -l app=ipam4lab --no-headers 2>/dev/null || echo "  None found"
echo ""
echo "🎉 Cleanup complete!"

# Show some helpful information
echo ""
echo "ℹ️  To redeploy IPAM4Lab:"
echo "   ./deploy.sh $NAMESPACE"
echo ""
echo "ℹ️  To deploy to a different namespace:"
echo "   ./deploy.sh my-new-namespace"

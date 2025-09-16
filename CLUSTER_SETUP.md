# OpenShift Cluster Setup Guide

## Connection to your OpenShift Cluster

Based on your SSH access: `ssh lab-user@ssh.ocpvdev01.rhdp.net -p 31295`

### Step 1: Connect to the cluster

```bash
# SSH to the jump host
ssh lab-user@ssh.ocpvdev01.rhdp.net -p 31295
```

### Step 2: Login to OpenShift

Once connected, you'll need to login to the OpenShift cluster. Try one of these methods:

```bash
# Method 1: If oc is already configured
oc whoami

# Method 2: Login with username/password
oc login

# Method 3: Login with token (get token from OpenShift web console)
oc login --token=YOUR_TOKEN --server=https://api.cluster.com:6443

# Method 4: Check if there's a kubeconfig already
export KUBECONFIG=/path/to/kubeconfig
oc whoami
```

### Step 3: Check cluster status

```bash
# Check if you're logged in
oc whoami
oc whoami --show-server

# Check available projects/namespaces
oc projects

# Check cluster nodes
oc get nodes
```

## Deployment Troubleshooting

### Option 1: Use the troubleshooting script

```bash
# Copy the project files to the cluster
scp -P 31295 -r . lab-user@ssh.ocpvdev01.rhdp.net:/tmp/ipam4lab/

# SSH to the cluster
ssh lab-user@ssh.ocpvdev01.rhdp.net -p 31295

# Run troubleshooting
cd /tmp/ipam4lab
./troubleshoot.sh
```

### Option 2: Simple deployment (no BuildConfig)

```bash
# Use the simple deployment that doesn't require S2I builds
./deploy-simple.sh ipam4lab
```

### Option 3: Manual step-by-step deployment

```bash
# 1. Create project
oc new-project ipam4lab

# 2. Check what went wrong in the original deployment
oc get all
oc get events --sort-by='.lastTimestamp' | tail -20

# 3. Check specific resource issues
oc describe deployment ipam4lab
oc describe pod <pod-name>
oc logs <pod-name>
```

## Common Issues in OpenShift Environments

### 1. Image Pull Issues
```bash
# Check if build completed
oc get builds
oc logs build/ipam4lab-build-1

# Check imagestream
oc get imagestream
oc describe imagestream ipam4lab
```

### 2. Security Context Issues
```bash
# Check for SCC issues
oc get events | grep -i "security\|scc\|forbidden"

# Try with different security context
oc adm policy add-scc-to-user anyuid -z default
```

### 3. Storage Issues
```bash
# Check PVC status
oc get pvc
oc describe pvc ipam4lab-data

# Check available storage classes
oc get storageclass
```

### 4. Network/Route Issues
```bash
# Check route status
oc get route
oc describe route ipam4lab-route

# Test internal connectivity
oc exec <pod-name> -- curl localhost:8080/health
```

## Alternative Deployment Methods

### Method A: Using existing Python image (Recommended for troubleshooting)

```bash
./deploy-simple.sh ipam4lab 192.168.0.0/16
```

This method:
- Uses a pre-built Python image
- Installs dependencies at runtime
- Avoids BuildConfig complexity
- More likely to work in restricted environments

### Method B: Using oc new-app

```bash
# Create from GitHub (if git is accessible)
oc new-app python:3.11~https://github.com/pnavarro/ipam4lab.git

# Or create from local directory
oc new-app python:3.11~. --name=ipam4lab
```

### Method C: Local build and push

```bash
# Build locally and push to internal registry
docker build -t ipam4lab .
docker tag ipam4lab default-route-openshift-image-registry.apps.cluster.com/ipam4lab/ipam4lab:latest
docker push default-route-openshift-image-registry.apps.cluster.com/ipam4lab/ipam4lab:latest

# Then deploy using the pushed image
oc new-app ipam4lab/ipam4lab:latest
```

## Quick Test Commands

```bash
# After deployment, test the service
ROUTE_URL=$(oc get route ipam4lab-route -o jsonpath='{.spec.host}')

# Health check
curl -k https://$ROUTE_URL/health

# Test allocation
curl -k -X POST https://$ROUTE_URL/allocate \
  -H "Content-Type: application/json" \
  -d '{"lab_uid": "test-001"}'

# List allocations
curl -k https://$ROUTE_URL/allocations
```

## Need Help?

Run the troubleshooting script to get a comprehensive view of what's happening:

```bash
./troubleshoot.sh ipam4lab
```

The script will show you:
- Current resource status
- Pod logs and events
- Common issues checklist
- Next steps recommendations

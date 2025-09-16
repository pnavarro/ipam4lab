# Ansible Integration with IPAM4Lab

This directory contains Ansible playbooks for integrating with the IPAM4Lab service.

## Playbooks

### 1. `ipam_allocation.yml`
Allocates IP addresses for a lab environment.

**Usage:**
```bash
# Allocate with auto-generated lab UID
ansible-playbook ipam_allocation.yml

# Allocate with specific lab UID
ansible-playbook ipam_allocation.yml -e lab_id=my-lab-001

# Use custom IPAM service URL
ansible-playbook ipam_allocation.yml -e ipam_service_url=https://ipam4lab.example.com -e lab_id=my-lab-001
```

**What it does:**
- Checks if allocation already exists
- Allocates new IP range if needed
- Exports environment variables to a shell script
- Adds allocated hosts to Ansible inventory for immediate use

### 2. `ipam_deallocation.yml`
Deallocates IP addresses for a lab environment.

**Usage:**
```bash
# Deallocate specific lab
ansible-playbook ipam_deallocation.yml -e lab_id=my-lab-001
```

**What it does:**
- Verifies the allocation exists
- Shows current allocation before deallocation
- Deallocates the IP range
- Cleans up environment files

### 3. `ipam_list.yml`
Lists all active lab allocations.

**Usage:**
```bash
ansible-playbook ipam_list.yml
```

**What it does:**
- Retrieves all active allocations
- Displays them in a readable format

## Configuration

Update the `ipam_service_url` variable in each playbook to match your IPAM4Lab service URL:

```yaml
vars:
  ipam_service_url: "https://ipam4lab-route-your-namespace.apps.your-cluster.com"
```

## Example Usage in a Complete Workflow

```bash
# 1. Allocate IP addresses
ansible-playbook ipam_allocation.yml -e lab_id=lab-demo-001

# 2. Use the allocated IPs in your main playbook
ansible-playbook -i inventory.yml your-lab-setup.yml

# 3. Clean up when done
ansible-playbook ipam_deallocation.yml -e lab_id=lab-demo-001
```

## Integration with Other Playbooks

After running `ipam_allocation.yml`, you can use the allocated IPs in other playbooks:

```yaml
- name: Configure lab environment
  hosts: workers
  tasks:
    - name: Install software on workers
      package:
        name: your-package
        state: present

- name: Configure conversion host
  hosts: conversion_hosts
  tasks:
    - name: Setup conversion service
      service:
        name: conversion-service
        state: started
```

## Environment Variables

The allocation playbook creates a shell script with the allocated IPs:

```bash
# Source the environment file
source ./lab_lab-demo-001_env.sh

# Use the variables
echo "Worker 1 IP: $EXTERNAL_IP_WORKER_1"
echo "Public network range: $PUBLIC_NET_START - $PUBLIC_NET_END"
```

# IPAM4Lab - IP Address Management for Lab Environments

IPAM4Lab is a Flask-based REST API service designed to allocate and manage IP address ranges for lab environments in OpenShift. It provides automatic IP allocation from a configurable network CIDR and maintains state in a SQLite database.

## Features

- **Automatic IP Allocation**: Allocates IP ranges from a configurable network CIDR (default: 192.168.0.0/16)
- **Cluster Support**: Supports multiple clusters with overlapping IP ranges
- **Persistent State**: Uses SQLite database to track allocations
- **RESTful API**: Simple HTTP endpoints for allocation, deallocation, and listing
- **OpenShift Ready**: Includes deployment manifests and BuildConfig
- **Ansible Integration**: Ready-to-use Ansible playbooks for automation
- **Thread Safe**: Supports concurrent requests with database locking

## Architecture

The application uses a shared IP allocation model where **all clusters use the same network CIDR**:

1. **Shared Network**: All clusters use the same configured CIDR (e.g., `192.168.0.0/16`)
2. **Overlapping Allocations**: Labs in different clusters can have identical IP addresses
3. **Cluster Isolation**: Despite using the same CIDR, clusters are logically separated
4. **Shared IP Pool**: All labs across all clusters share the same 65,534 usable IPs from `192.168.0.0/16`
5. **Individual IPs**: Each lab gets 16 specific individual IP addresses from the shared pool

### IP Allocation Pattern

Each lab gets **16 individual IP addresses** sequentially from its cluster's shared `/16` network:
- **3 Worker IPs**: EXTERNAL_IP_WORKER_1, EXTERNAL_IP_WORKER_2, EXTERNAL_IP_WORKER_3
- **1 Bastion IP**: EXTERNAL_IP_BASTION
- **12 Public Range IPs**: Including PUBLIC_NET_START, PUBLIC_NET_END, and CONVERSION_HOST_IP
  - **PUBLIC_NET_START**: First IP of the range
  - **PUBLIC_NET_END**: Last IP of the range (12 IPs total in range)
  - **CONVERSION_HOST_IP**: One IP within the public range (10 available IPs between start and end)
  - **10 Available IPs**: Between PUBLIC_NET_START and PUBLIC_NET_END for lab use

### Example Allocations

**All clusters share the same network**: `192.168.0.0/16` *(63,998 total usable IPs, excluding protected ranges)*

**Note**: With protected ranges enabled, actual allocations will start from `192.168.4.x` range, but the examples below show the allocation pattern.

**First allocation** (`test-001` in cluster `ocpv04`):
```
EXTERNAL_IP_WORKER_1=192.168.0.1   # First available IP
EXTERNAL_IP_WORKER_2=192.168.0.2   # Second available IP  
EXTERNAL_IP_WORKER_3=192.168.0.3   # Third available IP
EXTERNAL_IP_BASTION=192.168.0.4     # Fourth available IP

# Public range: 12 consecutive IPs
PUBLIC_NET_START=192.168.0.5        # Start of public range
# IPs 192.168.0.6 through 192.168.0.15 are available for lab use
CONVERSION_HOST_IP=192.168.0.11     # One IP within the public range  
PUBLIC_NET_END=192.168.0.16         # End of public range
# 10 available IPs between start and end: .6, .7, .8, .9, .10, .11, .12, .13, .14, .15
```

**Second allocation** (`test-002` in cluster `ocpv04`):
```
EXTERNAL_IP_WORKER_1=192.168.0.17  # Next available IP (continues sequentially)
EXTERNAL_IP_WORKER_2=192.168.0.18  # Next available IP
EXTERNAL_IP_WORKER_3=192.168.0.19  # Next available IP
EXTERNAL_IP_BASTION=192.168.0.20    # Next available IP

# Public range: next 12 consecutive IPs
PUBLIC_NET_START=192.168.0.21       # Start of public range
# IPs 192.168.0.22 through 192.168.0.31 are available for lab use
CONVERSION_HOST_IP=192.168.0.27     # One IP within the public range
PUBLIC_NET_END=192.168.0.32         # End of public range
# 10 available IPs between start and end: .22, .23, .24, .25, .26, .27, .28, .29, .30, .31
```

**Third allocation** (`test-001` in cluster `ocpv05`):
```
EXTERNAL_IP_WORKER_1=192.168.0.1    # Same IP as cluster ocpv04 - overlapping allocation!
EXTERNAL_IP_WORKER_2=192.168.0.2    # Same IP addresses can be used in different clusters
EXTERNAL_IP_WORKER_3=192.168.0.3    # Clusters logically isolated despite same CIDR
EXTERNAL_IP_BASTION=192.168.0.4     # No IP conflicts - overlapping by design

# Public range: 12 consecutive IPs (same as ocpv04 - overlapping allocation)
PUBLIC_NET_START=192.168.0.5        # Start of public range  
CONVERSION_HOST_IP=192.168.0.11     # One IP within the public range
PUBLIC_NET_END=192.168.0.16         # End of public range
# 10 available IPs between start and end: .6, .7, .8, .9, .10, .11, .12, .13, .14, .15
```

**Fourth allocation** (`test-002` in cluster `ocpv05`):
```
EXTERNAL_IP_WORKER_1=192.168.0.17   # Continues from same shared pool
EXTERNAL_IP_WORKER_2=192.168.0.18   # Same pattern - clusters track their own allocations
EXTERNAL_IP_WORKER_3=192.168.0.19   # IP overlap with ocpv04 is allowed and expected
EXTERNAL_IP_BASTION=192.168.0.20    # Each cluster manages its own labs

# Public range: next 12 consecutive IPs
PUBLIC_NET_START=192.168.0.21       # Start of public range
CONVERSION_HOST_IP=192.168.0.27     # One IP within the public range
PUBLIC_NET_END=192.168.0.32         # End of public range  
# 10 available IPs between start and end: .22, .23, .24, .25, .26, .27, .28, .29, .30, .31
```

### IP Overlap Between Clusters

**✅ IP addresses CAN and DO overlap between different clusters**

- **Shared CIDR**: All clusters use the same network CIDR (`192.168.0.0/16`)
- **Identical IPs Allowed**: Lab `test-001` in `ocpv04` and `ocpv05` both use `192.168.0.1`
- **Logical Separation**: Clusters are isolated in the application layer, not network layer
- **Overlapping by Design**: Same IP addresses are intentionally reused across clusters

**Example of intentional IP overlap:**
```bash
# Cluster ocpv04 (shared 192.168.0.0/16):
test-001: EXTERNAL_IP_WORKER_1=192.168.0.1

# Cluster ocpv05 (same 192.168.0.0/16): 
test-001: EXTERNAL_IP_WORKER_1=192.168.0.1  # Exact same IP in different cluster

# Both labs can coexist with identical IPs!
```

### Capacity

- **Shared Pool**: All clusters share the same **63,998 usable IPs** from `192.168.0.0/16`
- **Protected Ranges**: **1,536 IPs reserved** for infrastructure and management (see Protected IP Ranges below)
- **Total Labs**: Up to **3,999 labs total** across all clusters (63,998 ÷ 16 IPs per lab)
- **IP Reuse**: Same IP addresses can be allocated in multiple clusters simultaneously
- **Efficient Usage**: Each cluster can allocate from the available IP range independently
- **Public IP Range**: Each lab gets 10 available IPs between PUBLIC_NET_START and PUBLIC_NET_END
- **Overlap Design**: Multiple clusters can have identical allocations without conflict

### Protected IP Ranges

To avoid conflicts with infrastructure and management systems, the following IP ranges are **protected** and will not be allocated to labs:

#### **Protected Subnets** (1,536 IPs total):
- **`192.168.0.0/24`** - First subnet, typically used for infrastructure
- **`192.168.1.0/24`** - Second subnet, typically used for infrastructure
- **`192.168.2.0/24`** - Third subnet, typically used for infrastructure
- **`192.168.3.0/24`** - Fourth subnet, typically used for infrastructure
- **`192.168.254.0/24`** - Second-to-last subnet, typically used for management
- **`192.168.255.0/24`** - Last subnet, typically used for management

#### **Protected Specific IPs**:
- **`192.168.0.1`** - Common default gateway
- **`192.168.0.254`** - Common gateway address
- **`192.168.1.1`** - Common gateway address
- **`192.168.1.254`** - Common gateway address

#### **Available Range for Lab Allocation**:
- **`192.168.4.1`** through **`192.168.253.254`** (excluding protected specific IPs)
- Labs will be allocated from these safe ranges only

## Quick Start

### Prerequisites

- Python 3.11+
- OpenShift cluster (for deployment)
- Docker/Podman (for building containers)

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd ipam4lab
   pip install -r requirements.txt
   ```

2. **Run locally**:
   ```bash
   export PUBLIC_NETWORK_CIDR="192.168.0.0/16"
   export DATABASE_PATH="./ipam.db"
   python app.py
   ```

3. **Test the API**:
   ```bash
   # Allocate IP range
   curl -X POST http://localhost:8080/allocate \
     -H "Content-Type: application/json" \
     -d '{"lab_uid": "lab-001"}'

   # Get allocation
   curl http://localhost:8080/allocation/lab-001

   # List all allocations
   curl http://localhost:8080/allocations

   # Deallocate
   curl -X DELETE http://localhost:8080/deallocate \
     -H "Content-Type: application/json" \
     -d '{"lab_uid": "lab-001"}'
   ```

## API Reference

### POST /allocate

Allocate IP range for a lab environment.

**Request:**
```json
{
  "lab_uid": "lab-001"
}
```

**Response (201):**
```json
{
  "lab_uid": "lab-001",
  "allocation": {
    "lab_uid": "lab-001",
    "subnet_start": "192.168.0.0",
    "subnet_end": "192.168.0.255",
    "external_ip_worker_1": "192.168.0.10",
    "external_ip_worker_2": "192.168.0.11",
    "external_ip_worker_3": "192.168.0.12",
    "public_net_start": "192.168.0.20",
    "public_net_end": "192.168.0.30",
    "conversion_host_ip": "192.168.0.29"
  },
  "env_vars": {
    "EXTERNAL_IP_WORKER_1": "192.168.0.10",
    "EXTERNAL_IP_WORKER_2": "192.168.0.11",
    "EXTERNAL_IP_WORKER_3": "192.168.0.12",
    "PUBLIC_NET_START": "192.168.0.20",
    "PUBLIC_NET_END": "192.168.0.30",
    "CONVERSION_HOST_IP": "192.168.0.29"
  }
}
```

### GET /allocation/{lab_uid}

Get existing allocation for a lab UID.

**Response (200):** Same format as allocation response above.

### DELETE /deallocate

Deallocate IP range for a lab environment.

**Request:**
```json
{
  "lab_uid": "lab-001"
}
```

**Response (200):**
```json
{
  "message": "Successfully deallocated network for lab_uid: lab-001"
}
```

### GET /allocations

List all active allocations.

**Response (200):**
```json
{
  "allocations": [
    {
      "lab_uid": "lab-001",
      "subnet_start": "192.168.0.0",
      "subnet_end": "192.168.0.255",
      "external_ip_worker_1": "192.168.0.10",
      "external_ip_worker_2": "192.168.0.11",
      "external_ip_worker_3": "192.168.0.12",
      "public_net_start": "192.168.0.20",
      "public_net_end": "192.168.0.30",
      "conversion_host_ip": "192.168.0.29",
      "allocated_at": "2024-01-01 12:00:00",
      "status": "active"
    }
  ]
}
```

### GET /health

Health check endpoint.

**Response (200):**
```json
{
  "status": "healthy",
  "network_cidr": "192.168.0.0/16"
}
```

### GET /stats

Get allocation statistics and capacity information.

**Response (200):**
```json
{
  "shared_network_cidr": "192.168.0.0/16",
  "total_active_lab_allocations": 5,
  "active_clusters": 3,
  "total_ips_in_network": 65534,
  "protected_ips_count": 1536,
  "total_ips_available": 63998,
  "total_allocated_ips": 80,
  "utilization_percent": 0.124,
  "ips_per_lab": 16,
  "estimated_max_total_labs": 3999,
  "note": "All clusters share the same network CIDR with overlapping IP allocations. Protected ranges are excluded from allocation.",
  "clusters": [
    {"cluster": "production", "network": "192.168.0.0/16"},
    {"cluster": "development", "network": "192.168.0.0/16"}
  ],
  "cluster_usage": [
    {"cluster": "production", "labs_allocated": 3},
    {"cluster": "development", "labs_allocated": 2}
  ]
}
```

### GET /protected-ranges

Get information about protected IP ranges that are not allocated to labs.

**Response (200):**
```json
{
  "protected_subnets": [
    "192.168.0.0/24",
    "192.168.1.0/24",
    "192.168.2.0/24",
    "192.168.3.0/24",
    "192.168.254.0/24",
    "192.168.255.0/24"
  ],
  "protected_specific_ips": [
    "192.168.0.1",
    "192.168.0.254",
    "192.168.1.1",
    "192.168.1.254"
  ],
  "total_protected_ips": 1536,
  "available_for_allocation": 63998,
  "note": "These IP ranges are reserved for infrastructure and will not be allocated to labs"
}
```

## OpenShift Deployment

### 1. Build and Deploy

```bash
# Deploy IPAM4Lab to OpenShift (handles all edge cases automatically)
./deploy.sh ipam4lab 192.168.0.0/16

# Or with default network CIDR
./deploy.sh

# Or specify only namespace
./deploy.sh my-namespace
```

The deployment script automatically handles:
- ✅ **Security Context Constraints** - Uses OpenShift-compatible security contexts
- ✅ **Image References** - Properly resolves internal registry image references
- ✅ **Build Management** - Waits for build completion and verifies success
- ✅ **Step-by-step Verification** - Checks each deployment stage
- ✅ **Error Handling** - Provides detailed error messages and logs
- ✅ **Health Checks** - Tests the deployed application

### 4. Undeploy

```bash
# Remove IPAM4Lab from OpenShift
./undeploy.sh ipam4lab

# Keep the namespace but remove the app
./undeploy.sh ipam4lab --keep-namespace

# Interactive prompts will ask about:
# - Confirming resource deletion
# - Deleting PVC (database data)
# - Deleting the namespace
```

### 2. Configuration

Update the ConfigMap to change the network CIDR:

```yaml
# openshift/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ipam4lab-config
data:
  public_network_cidr: "10.0.0.0/16"  # Change as needed
```

### 3. Access the Service

```bash
# Get the route URL
oc get route ipam4lab-route

# Test the service
curl https://$(oc get route ipam4lab-route -o jsonpath='{.spec.host}')/health
```

## Cluster Support

IPAM4Lab supports multiple clusters with **identical shared CIDR and overlapping IP allocations**. All clusters use the same network CIDR (`192.168.0.0/16`) and can allocate identical IP addresses without conflicts.

**Key Benefits:**
- **Shared CIDR**: All clusters use the same `192.168.0.0/16` network
- **IP Reuse**: Identical IP addresses (e.g., `192.168.0.1`) can be allocated in multiple clusters simultaneously
- **Predictable Addressing**: Labs get consistent IP patterns regardless of cluster
- **Logical Isolation**: Clusters are separated at the application level, not network level
- **Resource Efficiency**: Every cluster can use the full IP range independently

### Using Clusters

**API Usage:**
```bash
# Allocate IPs for a lab in a specific cluster
curl -X POST https://ipam4lab.example.com/allocate \
  -H "Content-Type: application/json" \
  -d '{"name": "my-lab", "cluster": "ocpv04"}'

# Get allocation for a specific cluster
curl "https://ipam4lab.example.com/allocation/my-lab?cluster=ocpv04"

# List all allocations in a cluster
curl "https://ipam4lab.example.com/allocations?cluster=ocpv04"

# Deallocate from a specific cluster
curl -X DELETE https://ipam4lab.example.com/deallocate \
  -H "Content-Type: application/json" \
  -d '{"name": "my-lab", "cluster": "ocpv04"}'
```

**Ansible Usage:**
```bash
# Allocate IPs for a lab in cluster ocpv04
ansible-playbook ansible/ipam_allocation.yml -e lab_id=my-lab -e cluster_name=ocpv04

# Clean up from specific cluster
ansible-playbook ansible/ipam_deallocation.yml -e lab_id=my-lab -e cluster_name=ocpv04
```

## Ansible Integration

The `ansible/` directory contains ready-to-use playbooks for automating IP allocation:

### Basic Usage

```bash
# Allocate IPs for a lab (default cluster)
ansible-playbook ansible/ipam_allocation.yml -e lab_id=my-lab

# Allocate IPs for a lab in specific cluster
ansible-playbook ansible/ipam_allocation.yml -e lab_id=my-lab -e cluster_name=ocpv04

# Use the allocated IPs in your infrastructure playbooks
ansible-playbook -i ansible/inventory.yml your-playbook.yml

# Clean up when done (default cluster)
ansible-playbook ansible/ipam_deallocation.yml -e lab_id=my-lab

# Clean up from specific cluster
ansible-playbook ansible/ipam_deallocation.yml -e lab_id=my-lab -e cluster_name=ocpv04
```

### Example in Infrastructure Automation

```yaml
---
- import_playbook: ansible/ipam_allocation.yml
  vars:
    lab_id: "{{ lab_environment_id }}"
    cluster_name: "{{ cluster_name | default('default') }}"
    ipam_service_url: "https://ipam4lab.example.com"

- name: Configure lab infrastructure
  hosts: workers
  tasks:
    - name: Deploy application
      # Use the allocated worker IPs
      template:
        src: app-config.j2
        dest: /etc/app/config.yml
      vars:
        worker_ips:
          - "{{ external_ip_worker_1 }}"
          - "{{ external_ip_worker_2 }}"
          - "{{ external_ip_worker_3 }}"
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBLIC_NETWORK_CIDR` | `192.168.0.0/16` | Network CIDR for IP allocation |
| `DATABASE_PATH` | `/data/ipam.db` | Path to SQLite database file |
| `PORT` | `8080` | Port for the Flask application |

### Database

The application uses SQLite with two main tables:

- **allocations**: Tracks active IP allocations per lab UID
- **subnet_tracking**: Tracks which /24 subnets are allocated

## Security Considerations

- The application runs as a non-root user in the container
- Database operations are thread-safe with proper locking
- HTTPS is enforced via OpenShift route configuration
- No sensitive data is logged

## Monitoring and Health Checks

- **Liveness Probe**: HTTP GET to `/health`
- **Readiness Probe**: HTTP GET to `/health`
- **Logs**: Application logs to stdout/stderr for OpenShift log aggregation

## Troubleshooting

### Common Issues

1. **"No available subnets"**: The configured network CIDR is exhausted
   - Solution: Use a larger CIDR (e.g., /8 instead of /16) or deallocate unused labs

2. **Database locked**: Multiple concurrent requests
   - Solution: The application handles this automatically with retries

3. **Route not accessible**: OpenShift route configuration issue
   - Solution: Check route status with `oc get route ipam4lab-route`

### Debugging

```bash
# Check application logs
oc logs deployment/ipam4lab

# Check database content
oc exec deployment/ipam4lab -- sqlite3 /data/ipam.db "SELECT * FROM allocations;"

# Test API directly from pod
oc exec deployment/ipam4lab -- curl localhost:8080/health
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

[MIT License](LICENSE) - See LICENSE file for details.

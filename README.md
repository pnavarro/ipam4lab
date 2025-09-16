# IPAM4Lab - IP Address Management for Lab Environments

IPAM4Lab is a Flask-based REST API service designed to allocate and manage IP address ranges for lab environments in OpenShift. It provides automatic IP allocation from a configurable network CIDR and maintains state in a SQLite database.

## Features

- **Automatic IP Allocation**: Allocates IP ranges from a configurable network CIDR (default: 192.168.0.0/16)
- **Persistent State**: Uses SQLite database to track allocations
- **RESTful API**: Simple HTTP endpoints for allocation, deallocation, and listing
- **OpenShift Ready**: Includes deployment manifests and BuildConfig
- **Ansible Integration**: Ready-to-use Ansible playbooks for automation
- **Thread Safe**: Supports concurrent requests with database locking

## Architecture

The application allocates /24 subnets from the configured network CIDR and assigns specific IPs within each subnet:

- **Worker IPs**: .10, .11, .12 (EXTERNAL_IP_WORKER_1, EXTERNAL_IP_WORKER_2, EXTERNAL_IP_WORKER_3)
- **Public Network Range**: .20 to .30 (PUBLIC_NET_START, PUBLIC_NET_END)
- **Conversion Host**: .29 (CONVERSION_HOST_IP)

### Example Allocation

For LAB_UID `lab-001` with network CIDR `192.168.0.0/16`, the first allocation would be:

```
EXTERNAL_IP_WORKER_1=192.168.0.10
EXTERNAL_IP_WORKER_2=192.168.0.11
EXTERNAL_IP_WORKER_3=192.168.0.12
PUBLIC_NET_START=192.168.0.20
PUBLIC_NET_END=192.168.0.30
CONVERSION_HOST_IP=192.168.0.29
```

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

## OpenShift Deployment

### 1. Build and Deploy

```bash
# Easy deployment with script
./deploy.sh ipam4lab 192.168.0.0/16

# Or manually:
# Create namespace
oc new-project ipam4lab

# Apply manifests
oc apply -f openshift/

# Wait for deployment
oc rollout status deployment/ipam4lab
```

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

## Ansible Integration

The `ansible/` directory contains ready-to-use playbooks for automating IP allocation:

### Basic Usage

```bash
# Allocate IPs for a lab
ansible-playbook ansible/ipam_allocation.yml -e lab_id=my-lab

# Use the allocated IPs in your infrastructure playbooks
ansible-playbook -i ansible/inventory.yml your-playbook.yml

# Clean up when done
ansible-playbook ansible/ipam_deallocation.yml -e lab_id=my-lab
```

### Example in Infrastructure Automation

```yaml
---
- import_playbook: ansible/ipam_allocation.yml
  vars:
    lab_id: "{{ lab_environment_id }}"
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

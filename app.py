#!/usr/bin/env python3
"""
IPAM4Lab - IP Address Management for Lab Environments
A Flask application to allocate IP ranges for lab environments in OpenShift
"""

import os
import sqlite3
import ipaddress
import logging
from flask import Flask, request, jsonify
from datetime import datetime
import threading

app = Flask(__name__)

# Configuration
DEFAULT_PUBLIC_NETWORK_CIDR = "192.168.0.0/16"
DATABASE_PATH = os.environ.get('DATABASE_PATH', '/data/ipam.db')
PUBLIC_NETWORK_CIDR = os.environ.get('PUBLIC_NETWORK_CIDR', DEFAULT_PUBLIC_NETWORK_CIDR)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread lock for database operations
db_lock = threading.Lock()

class IPAMManager:
    def __init__(self, db_path, network_cidr):
        self.db_path = db_path
        self.base_network = ipaddress.IPv4Network(network_cidr)
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create allocations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lab_uid TEXT NOT NULL,
                    cluster TEXT NOT NULL,
                    subnet_start TEXT NOT NULL,
                    subnet_end TEXT NOT NULL,
                    external_ip_worker_1 TEXT NOT NULL,
                    external_ip_worker_2 TEXT NOT NULL,
                    external_ip_worker_3 TEXT NOT NULL,
                    external_ip_bastion TEXT NOT NULL,
                    public_net_start TEXT NOT NULL,
                    public_net_end TEXT NOT NULL,
                    conversion_host_ip TEXT NOT NULL,
                    allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    UNIQUE(lab_uid, cluster)
                )
            ''')
            
            # Add the new external_ip_bastion column if it doesn't exist (for existing databases)
            try:
                cursor.execute('ALTER TABLE allocations ADD COLUMN external_ip_bastion TEXT')
            except sqlite3.OperationalError:
                # Column already exists, ignore the error
                pass
            
            # Add cluster column if it doesn't exist (for existing databases)
            try:
                cursor.execute('ALTER TABLE allocations ADD COLUMN cluster TEXT DEFAULT "default"')
            except sqlite3.OperationalError:
                # Column already exists, ignore the error
                pass
            
            # Create cluster networks table to track /16 assignments per cluster
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cluster_networks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster TEXT UNIQUE NOT NULL,
                    network_cidr TEXT NOT NULL,
                    allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create IP tracking table for individual IP allocation within cluster networks
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ip_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    cluster TEXT NOT NULL,
                    lab_uid TEXT,
                    ip_type TEXT NOT NULL,  -- 'worker1', 'worker2', 'worker3', 'bastion', 'conversion'
                    allocated BOOLEAN DEFAULT FALSE,
                    allocated_at TIMESTAMP,
                    UNIQUE(ip_address, cluster)
                )
            ''')
            
            conn.commit()
            conn.close()
    
    def get_or_create_cluster_network(self, cluster="default"):
        """Get the shared /16 network for all clusters (all clusters use the same CIDR)"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if cluster already has a network assigned
            cursor.execute('SELECT network_cidr FROM cluster_networks WHERE cluster = ?', (cluster,))
            result = cursor.fetchone()
            
            if result:
                conn.close()
                return ipaddress.IPv4Network(result[0])
            
            # All clusters use the same base network CIDR (e.g., 192.168.0.0/16)
            shared_network_str = str(self.base_network)
            
            # Assign the same base network to this cluster
            cursor.execute('''
                INSERT INTO cluster_networks (cluster, network_cidr)
                VALUES (?, ?)
            ''', (cluster, shared_network_str))
            conn.commit()
            conn.close()
            logger.info(f"Assigned shared network {shared_network_str} to cluster {cluster}")
            return self.base_network
    
    def is_protected_ip(self, ip_str):
        """Check if an IP address is in a protected range that should not be allocated"""
        ip = ipaddress.IPv4Address(ip_str)
        
        # Define protected IP ranges within 192.168.0.0/16
        protected_ranges = [
            ipaddress.IPv4Network('192.168.0.0/24'),    # First subnet - often used for infrastructure
            ipaddress.IPv4Network('192.168.1.0/24'),    # Second subnet - often used for infrastructure  
            ipaddress.IPv4Network('192.168.255.0/24'),  # Last subnet - often used for management
            ipaddress.IPv4Network('192.168.254.0/24'),  # Second to last - often used for management
        ]
        
        # Check specific protected IPs
        protected_ips = [
            ipaddress.IPv4Address('192.168.0.1'),       # Default gateway
            ipaddress.IPv4Address('192.168.0.254'),     # Common gateway
            ipaddress.IPv4Address('192.168.1.1'),       # Common gateway
            ipaddress.IPv4Address('192.168.1.254'),     # Common gateway
        ]
        
        # Check if IP is in any protected range
        for protected_range in protected_ranges:
            if ip in protected_range:
                return True
                
        # Check if IP is a specific protected IP
        if ip in protected_ips:
            return True
            
        return False
    
    def get_next_available_ips(self, cluster="default", count=16):
        """Get next available sequential IPs from cluster's /16 network, avoiding protected ranges"""
        # Get or create the /16 network for this cluster
        cluster_network = self.get_or_create_cluster_network(cluster)
        
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all allocated IPs for this cluster
            cursor.execute('SELECT ip_address FROM ip_tracking WHERE allocated = TRUE AND cluster = ?', (cluster,))
            allocated_ips = set(row[0] for row in cursor.fetchall())
            
            # Find sequential available IPs, skipping protected ranges
            available_ips = []
            for ip in cluster_network.hosts():
                ip_str = str(ip)
                # Skip if IP is already allocated or in protected range
                if ip_str not in allocated_ips and not self.is_protected_ip(ip_str):
                    available_ips.append(ip_str)
                    if len(available_ips) >= count:
                        break
            
            conn.close()
            
            if len(available_ips) < count:
                raise ValueError(f"Not enough available IPs in cluster {cluster}. Need {count}, found {len(available_ips)} (excluding protected ranges)")
            
            return available_ips[:count]
    
    
    def allocate_lab_network(self, lab_uid, cluster="default"):
        """Allocate individual IPs for a lab environment from cluster's shared /16 network"""
        if self.get_allocation(lab_uid, cluster):
            raise ValueError(f"Lab UID {lab_uid} already has an allocation in cluster {cluster}")
        
        # Get next available IPs from cluster's shared /16 network
        # We need 16 IPs: 3 workers + 1 bastion + 12 for public range (including conversion host)
        available_ips = self.get_next_available_ips(cluster, count=16)
        
        # Assign IPs according to the pattern
        external_ip_worker_1 = available_ips[0]  # First IP: Worker 1
        external_ip_worker_2 = available_ips[1]  # Second IP: Worker 2
        external_ip_worker_3 = available_ips[2]  # Third IP: Worker 3
        external_ip_bastion = available_ips[3]   # Fourth IP: Bastion
        
        # Public range: next 12 IPs (available_ips[4] through available_ips[15])
        # This gives us PUBLIC_NET_START to PUBLIC_NET_END with 10 available IPs between them
        public_net_start = available_ips[4]      # Fifth IP: Start of public range
        public_net_end = available_ips[15]       # Sixteenth IP: End of public range (12 total IPs in range, 10 available between start/end)
        
        # Conversion host: one of the available IPs in the middle of the public range
        conversion_host_ip = available_ips[10]   # Eleventh IP: Within the public range
        
        # Get cluster network for subnet info
        cluster_network = self.get_or_create_cluster_network(cluster)
        
        allocation = {
            'lab_uid': lab_uid,
            'cluster': cluster,
            'subnet_start': str(cluster_network.network_address),
            'subnet_end': str(cluster_network.broadcast_address),
            'external_ip_worker_1': external_ip_worker_1,
            'external_ip_worker_2': external_ip_worker_2,
            'external_ip_worker_3': external_ip_worker_3,
            'external_ip_bastion': external_ip_bastion,
            'public_net_start': public_net_start,
            'public_net_end': public_net_end,
            'conversion_host_ip': conversion_host_ip
        }
        
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Insert allocation
                cursor.execute('''
                    INSERT INTO allocations 
                    (lab_uid, cluster, subnet_start, subnet_end, external_ip_worker_1, 
                     external_ip_worker_2, external_ip_worker_3, external_ip_bastion,
                     public_net_start, public_net_end, conversion_host_ip)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lab_uid, cluster, allocation['subnet_start'], allocation['subnet_end'],
                    allocation['external_ip_worker_1'], allocation['external_ip_worker_2'],
                    allocation['external_ip_worker_3'], allocation['external_ip_bastion'],
                    allocation['public_net_start'], allocation['public_net_end'], 
                    allocation['conversion_host_ip']
                ))
                
                # Mark all 16 individual IPs as allocated in the IP tracking table
                ip_assignments = []
                
                # Worker and bastion IPs
                ip_assignments.extend([
                    (external_ip_worker_1, 'worker1'),
                    (external_ip_worker_2, 'worker2'),
                    (external_ip_worker_3, 'worker3'),
                    (external_ip_bastion, 'bastion'),
                ])
                
                # All 12 IPs in the public range (including conversion host)
                for i in range(4, 16):  # available_ips[4] through available_ips[15]
                    ip_address = available_ips[i]
                    if ip_address == conversion_host_ip:
                        ip_type = 'conversion'
                    elif ip_address == public_net_start:
                        ip_type = 'public_start'
                    elif ip_address == public_net_end:
                        ip_type = 'public_end'
                    else:
                        ip_type = 'public_range'
                    
                    ip_assignments.append((ip_address, ip_type))
                
                for ip_address, ip_type in ip_assignments:
                    cursor.execute('''
                        INSERT INTO ip_tracking 
                        (ip_address, cluster, lab_uid, ip_type, allocated, allocated_at)
                        VALUES (?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP)
                    ''', (ip_address, cluster, lab_uid, ip_type))
                
                conn.commit()
                logger.info(f"Allocated {len(ip_assignments)} IPs for lab_uid: {lab_uid} in cluster: {cluster}")
                return allocation
                
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
    
    def get_allocation(self, lab_uid, cluster="default"):
        """Get existing allocation for a lab UID in a specific cluster"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT lab_uid, cluster, subnet_start, subnet_end, external_ip_worker_1,
                       external_ip_worker_2, external_ip_worker_3, external_ip_bastion,
                       public_net_start, public_net_end, conversion_host_ip, allocated_at, status
                FROM allocations WHERE lab_uid = ? AND cluster = ? AND status = 'active'
            ''', (lab_uid, cluster))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'lab_uid': row[0],
                    'cluster': row[1],
                    'subnet_start': row[2],
                    'subnet_end': row[3],
                    'external_ip_worker_1': row[4],
                    'external_ip_worker_2': row[5],
                    'external_ip_worker_3': row[6],
                    'external_ip_bastion': row[7],
                    'public_net_start': row[8],
                    'public_net_end': row[9],
                    'conversion_host_ip': row[10],
                    'allocated_at': row[11],
                    'status': row[12]
                }
            return None
    
    def deallocate_lab_network(self, lab_uid, cluster="default"):
        """Deallocate individual IPs for a lab environment"""
        allocation = self.get_allocation(lab_uid, cluster)
        if not allocation:
            raise ValueError(f"No active allocation found for lab_uid: {lab_uid} in cluster: {cluster}")
        
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Mark allocation as inactive
                cursor.execute('''
                    UPDATE allocations SET status = 'inactive' 
                    WHERE lab_uid = ? AND cluster = ? AND status = 'active'
                ''', (lab_uid, cluster))
                
                # Mark individual IPs as available for this cluster
                cursor.execute('''
                    UPDATE ip_tracking SET allocated = FALSE, lab_uid = NULL
                    WHERE lab_uid = ? AND cluster = ?
                ''', (lab_uid, cluster))
                
                conn.commit()
                logger.info(f"Deallocated IPs for lab_uid: {lab_uid} in cluster: {cluster}")
                return True
                
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
    
    def list_allocations(self, cluster=None):
        """List all active allocations, optionally filtered by cluster"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if cluster:
                cursor.execute('''
                    SELECT lab_uid, cluster, subnet_start, subnet_end, external_ip_worker_1,
                           external_ip_worker_2, external_ip_worker_3, external_ip_bastion,
                           public_net_start, public_net_end, conversion_host_ip, allocated_at, status
                    FROM allocations WHERE status = 'active' AND cluster = ?
                    ORDER BY allocated_at DESC
                ''', (cluster,))
            else:
                cursor.execute('''
                    SELECT lab_uid, cluster, subnet_start, subnet_end, external_ip_worker_1,
                           external_ip_worker_2, external_ip_worker_3, external_ip_bastion,
                           public_net_start, public_net_end, conversion_host_ip, allocated_at, status
                    FROM allocations WHERE status = 'active'
                    ORDER BY allocated_at DESC
                ''')
            
            allocations = []
            for row in cursor.fetchall():
                allocations.append({
                    'lab_uid': row[0],
                    'cluster': row[1],
                    'subnet_start': row[2],
                    'subnet_end': row[3],
                    'external_ip_worker_1': row[4],
                    'external_ip_worker_2': row[5],
                    'external_ip_worker_3': row[6],
                    'external_ip_bastion': row[7],
                    'public_net_start': row[8],
                    'public_net_end': row[9],
                    'conversion_host_ip': row[10],
                    'allocated_at': row[11],
                    'status': row[12]
                })
            
            conn.close()
            return allocations
    
    def get_allocation_stats(self, cluster=None):
        """Get allocation statistics and capacity information"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if cluster:
                # Stats for specific cluster
                cursor.execute('SELECT COUNT(*) FROM allocations WHERE status = "active" AND cluster = ?', (cluster,))
                active_allocations = cursor.fetchone()[0]
                
                # Get cluster network
                cursor.execute('SELECT network_cidr FROM cluster_networks WHERE cluster = ?', (cluster,))
                cluster_network_result = cursor.fetchone()
                if cluster_network_result:
                    cluster_network = ipaddress.IPv4Network(cluster_network_result[0])
                    # Count total usable IPs in the /16 network (65534 for /16)
                    total_ips = cluster_network.num_addresses - 2  # Exclude network and broadcast
                    # Count allocated IPs
                    cursor.execute('SELECT COUNT(*) FROM ip_tracking WHERE allocated = TRUE AND cluster = ?', (cluster,))
                    allocated_ips = cursor.fetchone()[0]
                    utilization_percent = (allocated_ips / total_ips) * 100 if total_ips > 0 else 0
                else:
                    total_ips = 65534  # Default /16 capacity
                    allocated_ips = 0
                    utilization_percent = 0
                
                # Get IP usage breakdown
                cursor.execute('''
                    SELECT ip_type, COUNT(*) as count
                    FROM ip_tracking 
                    WHERE allocated = TRUE AND cluster = ?
                    GROUP BY ip_type
                    ORDER BY ip_type
                ''', (cluster,))
                
                ip_usage = []
                for row in cursor.fetchall():
                    ip_usage.append({
                        'ip_type': row[0],
                        'count': row[1]
                    })
                
                stats = {
                    'base_network_cidr': str(self.base_network),
                    'cluster': cluster,
                    'cluster_network': cluster_network_result[0] if cluster_network_result else None,
                    'active_lab_allocations': active_allocations,
                    'total_ips_in_cluster': total_ips,
                    'allocated_ips': allocated_ips,
                    'available_ips': total_ips - allocated_ips,
                    'utilization_percent': round(utilization_percent, 3),
                    'ips_per_lab': 16,  # Each lab gets 16 IPs (3 workers + 1 bastion + 12 for public range)
                    'estimated_max_labs': (total_ips - allocated_ips) // 16,
                    'ip_usage_by_type': ip_usage
                }
                    
            else:
                # Global stats across all clusters
                cursor.execute('SELECT COUNT(*) FROM allocations WHERE status = "active"')
                total_active_allocations = cursor.fetchone()[0]
                
                # Get cluster information
                cursor.execute('SELECT cluster, network_cidr FROM cluster_networks ORDER BY cluster')
                clusters = cursor.fetchall()
                
                # Since all clusters share the same /16 network, total capacity is base network minus protected ranges
                total_ips_in_network = self.base_network.num_addresses - 2  # Usable IPs (excluding network/broadcast)
                protected_ips_count = 1024  # 4 x /24 subnets = 1024 protected IPs
                total_ips_possible = total_ips_in_network - protected_ips_count  # Available for allocation
                
                # Count total allocated IPs across all clusters
                cursor.execute('SELECT COUNT(*) FROM ip_tracking WHERE allocated = TRUE')
                total_allocated_ips = cursor.fetchone()[0]
                
                utilization_percent = (total_allocated_ips / total_ips_possible) * 100 if total_ips_possible > 0 else 0
                
                # Get per-cluster allocation counts
                cursor.execute('''
                    SELECT cluster, COUNT(*) as count
                    FROM allocations 
                    WHERE status = "active"
                    GROUP BY cluster
                    ORDER BY cluster
                ''')
                
                cluster_usage = []
                for row in cursor.fetchall():
                    cluster_usage.append({
                        'cluster': row[0],
                        'labs_allocated': row[1]
                    })
                
                stats = {
                    'shared_network_cidr': str(self.base_network),
                    'total_active_lab_allocations': total_active_allocations,
                    'active_clusters': len(clusters),
                    'total_ips_in_network': total_ips_in_network,
                    'protected_ips_count': protected_ips_count,
                    'total_ips_available': total_ips_possible,
                    'total_allocated_ips': total_allocated_ips,
                    'utilization_percent': round(utilization_percent, 3),
                    'ips_per_lab': 16,
                    'estimated_max_total_labs': (total_ips_possible - total_allocated_ips) // 16,
                    'note': 'All clusters share the same network CIDR with overlapping IP allocations. Protected ranges are excluded from allocation.',
                    'clusters': [{'cluster': c[0], 'network': c[1]} for c in clusters],
                    'cluster_usage': cluster_usage
                }
            
            conn.close()
            return stats

# Initialize IPAM manager
ipam = IPAMManager(DATABASE_PATH, PUBLIC_NETWORK_CIDR)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'network_cidr': PUBLIC_NETWORK_CIDR})

@app.route('/allocate', methods=['POST'])
def allocate():
    """Allocate IP range for a lab environment"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'name is required'}), 400
        
        lab_uid = data['name']
        if not lab_uid or not isinstance(lab_uid, str):
            return jsonify({'error': 'name must be a non-empty string'}), 400
        
        # Get cluster parameter, default to "default" if not provided
        cluster = data.get('cluster', 'default')
        if not isinstance(cluster, str):
            return jsonify({'error': 'cluster must be a string'}), 400
        
        allocation = ipam.allocate_lab_network(lab_uid, cluster)
        
        # Format response as environment variables
        response = {
            'name': lab_uid,
            'cluster': cluster,
            'subnet': f"{allocation['subnet_start']}/24",
            'network': f"{allocation['subnet_start']}/24",
            'allocation': {
                'EXTERNAL_IP_WORKER_1': allocation['external_ip_worker_1'],
                'EXTERNAL_IP_WORKER_2': allocation['external_ip_worker_2'],
                'EXTERNAL_IP_WORKER_3': allocation['external_ip_worker_3'],
                'EXTERNAL_IP_BASTION': allocation['external_ip_bastion'],
                'PUBLIC_NET_START': allocation['public_net_start'],
                'PUBLIC_NET_END': allocation['public_net_end'],
                'CONVERSION_HOST_IP': allocation['conversion_host_ip']
            },
            'env_vars': {
                'EXTERNAL_IP_WORKER_1': allocation['external_ip_worker_1'],
                'EXTERNAL_IP_WORKER_2': allocation['external_ip_worker_2'],
                'EXTERNAL_IP_WORKER_3': allocation['external_ip_worker_3'],
                'EXTERNAL_IP_BASTION': allocation['external_ip_bastion'],
                'PUBLIC_NET_START': allocation['public_net_start'],
                'PUBLIC_NET_END': allocation['public_net_end'],
                'CONVERSION_HOST_IP': allocation['conversion_host_ip']
            }
        }
        
        return jsonify(response), 201
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error allocating network: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/allocation/<lab_uid>', methods=['GET'])
def get_allocation(lab_uid):
    """Get existing allocation for a lab UID"""
    try:
        # Get cluster parameter from query string, default to "default"
        cluster = request.args.get('cluster', 'default')
        
        allocation = ipam.get_allocation(lab_uid, cluster)
        if not allocation:
            return jsonify({'error': f'No allocation found for lab_uid: {lab_uid} in cluster: {cluster}'}), 404
        
        # Format response as environment variables
        response = {
            'name': lab_uid,
            'cluster': cluster,
            'subnet': f"{allocation['subnet_start']}/24",
            'network': f"{allocation['subnet_start']}/24",
            'allocation': {
                'EXTERNAL_IP_WORKER_1': allocation['external_ip_worker_1'],
                'EXTERNAL_IP_WORKER_2': allocation['external_ip_worker_2'],
                'EXTERNAL_IP_WORKER_3': allocation['external_ip_worker_3'],
                'EXTERNAL_IP_BASTION': allocation['external_ip_bastion'],
                'PUBLIC_NET_START': allocation['public_net_start'],
                'PUBLIC_NET_END': allocation['public_net_end'],
                'CONVERSION_HOST_IP': allocation['conversion_host_ip']
            },
            'env_vars': {
                'EXTERNAL_IP_WORKER_1': allocation['external_ip_worker_1'],
                'EXTERNAL_IP_WORKER_2': allocation['external_ip_worker_2'],
                'EXTERNAL_IP_WORKER_3': allocation['external_ip_worker_3'],
                'EXTERNAL_IP_BASTION': allocation['external_ip_bastion'],
                'PUBLIC_NET_START': allocation['public_net_start'],
                'PUBLIC_NET_END': allocation['public_net_end'],
                'CONVERSION_HOST_IP': allocation['conversion_host_ip']
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error getting allocation: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/deallocate', methods=['DELETE'])
def deallocate():
    """Deallocate IP range for a lab environment"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'name is required'}), 400
        
        lab_uid = data['name']
        # Get cluster parameter, default to "default" if not provided
        cluster = data.get('cluster', 'default')
        if not isinstance(cluster, str):
            return jsonify({'error': 'cluster must be a string'}), 400
        
        ipam.deallocate_lab_network(lab_uid, cluster)
        
        return jsonify({'message': f'Successfully deallocated network for lab_uid: {lab_uid} in cluster: {cluster}'})
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error deallocating network: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/allocations', methods=['GET'])
def list_allocations():
    """List all active allocations, optionally filtered by cluster"""
    try:
        # Get cluster parameter from query string, optional
        cluster = request.args.get('cluster')
        
        allocations = ipam.list_allocations(cluster)
        return jsonify({'allocations': allocations})
        
    except Exception as e:
        logger.error(f"Error listing allocations: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get allocation statistics and capacity information"""
    try:
        stats = ipam.get_allocation_stats()
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/protected-ranges', methods=['GET'])
def get_protected_ranges():
    """Get information about protected IP ranges that are not allocated"""
    try:
        protected_info = {
            'protected_subnets': [
                '192.168.0.0/24',   # First subnet - infrastructure
                '192.168.1.0/24',   # Second subnet - infrastructure
                '192.168.254.0/24', # Second to last - management
                '192.168.255.0/24'  # Last subnet - management
            ],
            'protected_specific_ips': [
                '192.168.0.1',      # Default gateway
                '192.168.0.254',    # Common gateway
                '192.168.1.1',      # Common gateway
                '192.168.1.254'     # Common gateway
            ],
            'total_protected_ips': 1024,  # 4 x 256 IPs per /24 subnet
            'available_for_allocation': 65534 - 1024,  # Total minus protected
            'note': 'These IP ranges are reserved for infrastructure and will not be allocated to labs'
        }
        return jsonify(protected_info)
        
    except Exception as e:
        logger.error(f"Error getting protected ranges: {e}")
        return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    # Run the application
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

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
        self.network = ipaddress.IPv4Network(network_cidr)
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
                    lab_uid TEXT UNIQUE NOT NULL,
                    subnet_start TEXT NOT NULL,
                    subnet_end TEXT NOT NULL,
                    external_ip_worker_1 TEXT NOT NULL,
                    external_ip_worker_2 TEXT NOT NULL,
                    external_ip_worker_3 TEXT NOT NULL,
                    public_net_start TEXT NOT NULL,
                    public_net_end TEXT NOT NULL,
                    conversion_host_ip TEXT NOT NULL,
                    allocated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # Create subnet tracking table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subnet_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subnet_cidr TEXT UNIQUE NOT NULL,
                    lab_uid TEXT,
                    allocated BOOLEAN DEFAULT FALSE,
                    allocated_at TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
    
    def get_next_available_subnet(self):
        """Get the next available /24 subnet from the network"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all allocated subnets
            cursor.execute('SELECT subnet_cidr FROM subnet_tracking WHERE allocated = TRUE')
            allocated_subnets = set(row[0] for row in cursor.fetchall())
            
            # Find first available /24 subnet
            for subnet in self.network.subnets(new_prefix=24):
                subnet_str = str(subnet)
                if subnet_str not in allocated_subnets:
                    conn.close()
                    return subnet
            
            conn.close()
            raise ValueError("No available subnets in the network range")
    
    def allocate_lab_network(self, lab_uid):
        """Allocate a network slice for a lab environment"""
        if self.get_allocation(lab_uid):
            raise ValueError(f"Lab UID {lab_uid} already has an allocation")
        
        # Get next available subnet
        subnet = self.get_next_available_subnet()
        subnet_hosts = list(subnet.hosts())
        
        if len(subnet_hosts) < 30:
            raise ValueError("Subnet too small for allocation")
        
        # Allocate specific IPs according to the pattern
        external_ip_worker_1 = str(subnet_hosts[10])  # .11
        external_ip_worker_2 = str(subnet_hosts[11])  # .12
        external_ip_worker_3 = str(subnet_hosts[12])  # .13
        public_net_start = str(subnet_hosts[19])      # .20
        public_net_end = str(subnet_hosts[29])        # .30
        conversion_host_ip = str(subnet_hosts[28])    # .29
        
        allocation = {
            'lab_uid': lab_uid,
            'subnet_start': str(subnet.network_address),
            'subnet_end': str(subnet.broadcast_address),
            'external_ip_worker_1': external_ip_worker_1,
            'external_ip_worker_2': external_ip_worker_2,
            'external_ip_worker_3': external_ip_worker_3,
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
                    (lab_uid, subnet_start, subnet_end, external_ip_worker_1, 
                     external_ip_worker_2, external_ip_worker_3, public_net_start, 
                     public_net_end, conversion_host_ip)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lab_uid, allocation['subnet_start'], allocation['subnet_end'],
                    allocation['external_ip_worker_1'], allocation['external_ip_worker_2'],
                    allocation['external_ip_worker_3'], allocation['public_net_start'],
                    allocation['public_net_end'], allocation['conversion_host_ip']
                ))
                
                # Mark subnet as allocated
                cursor.execute('''
                    INSERT OR REPLACE INTO subnet_tracking 
                    (subnet_cidr, lab_uid, allocated, allocated_at)
                    VALUES (?, ?, TRUE, CURRENT_TIMESTAMP)
                ''', (str(subnet), lab_uid))
                
                conn.commit()
                logger.info(f"Allocated network for lab_uid: {lab_uid}")
                return allocation
                
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
    
    def get_allocation(self, lab_uid):
        """Get existing allocation for a lab UID"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT lab_uid, subnet_start, subnet_end, external_ip_worker_1,
                       external_ip_worker_2, external_ip_worker_3, public_net_start,
                       public_net_end, conversion_host_ip, allocated_at, status
                FROM allocations WHERE lab_uid = ? AND status = 'active'
            ''', (lab_uid,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'lab_uid': row[0],
                    'subnet_start': row[1],
                    'subnet_end': row[2],
                    'external_ip_worker_1': row[3],
                    'external_ip_worker_2': row[4],
                    'external_ip_worker_3': row[5],
                    'public_net_start': row[6],
                    'public_net_end': row[7],
                    'conversion_host_ip': row[8],
                    'allocated_at': row[9],
                    'status': row[10]
                }
            return None
    
    def deallocate_lab_network(self, lab_uid):
        """Deallocate network for a lab environment"""
        allocation = self.get_allocation(lab_uid)
        if not allocation:
            raise ValueError(f"No active allocation found for lab_uid: {lab_uid}")
        
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # Mark allocation as inactive
                cursor.execute('''
                    UPDATE allocations SET status = 'inactive' 
                    WHERE lab_uid = ? AND status = 'active'
                ''', (lab_uid,))
                
                # Mark subnet as available
                cursor.execute('''
                    UPDATE subnet_tracking SET allocated = FALSE, lab_uid = NULL
                    WHERE lab_uid = ?
                ''', (lab_uid,))
                
                conn.commit()
                logger.info(f"Deallocated network for lab_uid: {lab_uid}")
                return True
                
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
    
    def list_allocations(self):
        """List all active allocations"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT lab_uid, subnet_start, subnet_end, external_ip_worker_1,
                       external_ip_worker_2, external_ip_worker_3, public_net_start,
                       public_net_end, conversion_host_ip, allocated_at, status
                FROM allocations WHERE status = 'active'
                ORDER BY allocated_at DESC
            ''')
            
            allocations = []
            for row in cursor.fetchall():
                allocations.append({
                    'lab_uid': row[0],
                    'subnet_start': row[1],
                    'subnet_end': row[2],
                    'external_ip_worker_1': row[3],
                    'external_ip_worker_2': row[4],
                    'external_ip_worker_3': row[5],
                    'public_net_start': row[6],
                    'public_net_end': row[7],
                    'conversion_host_ip': row[8],
                    'allocated_at': row[9],
                    'status': row[10]
                })
            
            conn.close()
            return allocations
    
    def get_allocation_stats(self):
        """Get allocation statistics and capacity information"""
        with db_lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Count active allocations
            cursor.execute('SELECT COUNT(*) FROM allocations WHERE status = "active"')
            active_allocations = cursor.fetchone()[0]
            
            # Calculate total capacity (number of /24 subnets available)
            total_capacity = 2 ** (24 - self.network.prefixlen)
            
            # Calculate utilization percentage
            utilization_percent = (active_allocations / total_capacity) * 100 if total_capacity > 0 else 0
            
            # Get subnet usage information
            cursor.execute('''
                SELECT subnet_start, COUNT(*) as count
                FROM allocations 
                WHERE status = "active"
                GROUP BY subnet_start
                ORDER BY subnet_start
            ''')
            
            subnet_usage = []
            for row in cursor.fetchall():
                subnet_usage.append({
                    'subnet': f"{row[0]}/24",
                    'labs_allocated': row[1]
                })
            
            conn.close()
            
            stats = {
                'network_cidr': str(self.network),
                'active_allocations': active_allocations,
                'total_capacity': total_capacity,
                'utilization_percent': round(utilization_percent, 3),
                'subnets_per_lab': 1,  # Each lab gets one /24 subnet
                'subnet_usage': subnet_usage,
                'next_available_subnet': None
            }
            
            # Try to get next available subnet
            try:
                next_subnet = self.get_next_available_subnet()
                stats['next_available_subnet'] = str(next_subnet)
            except ValueError:
                stats['next_available_subnet'] = None
            
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
        if not data or 'lab_uid' not in data:
            return jsonify({'error': 'lab_uid is required'}), 400
        
        lab_uid = data['lab_uid']
        if not lab_uid or not isinstance(lab_uid, str):
            return jsonify({'error': 'lab_uid must be a non-empty string'}), 400
        
        allocation = ipam.allocate_lab_network(lab_uid)
        
        # Format response as environment variables
        response = {
            'lab_uid': lab_uid,
            'allocation': allocation,
            'env_vars': {
                'EXTERNAL_IP_WORKER_1': allocation['external_ip_worker_1'],
                'EXTERNAL_IP_WORKER_2': allocation['external_ip_worker_2'],
                'EXTERNAL_IP_WORKER_3': allocation['external_ip_worker_3'],
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
        allocation = ipam.get_allocation(lab_uid)
        if not allocation:
            return jsonify({'error': f'No allocation found for lab_uid: {lab_uid}'}), 404
        
        # Format response as environment variables
        response = {
            'lab_uid': lab_uid,
            'allocation': allocation,
            'env_vars': {
                'EXTERNAL_IP_WORKER_1': allocation['external_ip_worker_1'],
                'EXTERNAL_IP_WORKER_2': allocation['external_ip_worker_2'],
                'EXTERNAL_IP_WORKER_3': allocation['external_ip_worker_3'],
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
        if not data or 'lab_uid' not in data:
            return jsonify({'error': 'lab_uid is required'}), 400
        
        lab_uid = data['lab_uid']
        ipam.deallocate_lab_network(lab_uid)
        
        return jsonify({'message': f'Successfully deallocated network for lab_uid: {lab_uid}'})
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error deallocating network: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/allocations', methods=['GET'])
def list_allocations():
    """List all active allocations"""
    try:
        allocations = ipam.list_allocations()
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

if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    # Run the application
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

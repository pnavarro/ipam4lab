#!/usr/bin/env python3
"""
Local test script for IPAM4Lab
Run this script to test the application locally before deployment
"""

import requests
import json
import time
import os
import sys

def test_ipam_service(base_url="http://localhost:8080"):
    """Test the IPAM service endpoints"""
    
    print("🧪 Testing IPAM4Lab Service")
    print(f"🌐 Base URL: {base_url}")
    print("-" * 50)
    
    # Test health endpoint
    print("1️⃣  Testing health endpoint...")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check failed: {e}")
        return False
    
    print()
    
    # Test allocation
    test_lab_uid = "test-lab-001"
    test_cluster = "test-cluster"
    print(f"2️⃣  Testing allocation for lab_uid: {test_lab_uid} in cluster: {test_cluster}")
    try:
        response = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid, "cluster": test_cluster},
            timeout=10
        )
        
        if response.status_code == 201:
            print("✅ Allocation successful")
            allocation_data = response.json()
            print(f"   Lab UID: {allocation_data['lab_uid']}")
            print(f"   Cluster: {allocation_data['allocation']['cluster']}")
            print("   Environment Variables:")
            for key, value in allocation_data['env_vars'].items():
                print(f"     {key}={value}")
            
            # Verify IP addresses are from shared 192.168.0.0/16 network
            worker_ip = allocation_data['env_vars']['EXTERNAL_IP_WORKER_1']
            if worker_ip.startswith('192.168.'):
                print("✅ IP allocation from shared 192.168.0.0/16 network confirmed")
        else:
            print(f"❌ Allocation failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Allocation failed: {e}")
        return False
    
    print()
    
    # Test getting allocation
    print(f"3️⃣  Testing get allocation for lab_uid: {test_lab_uid} in cluster: {test_cluster}")
    try:
        response = requests.get(f"{base_url}/allocation/{test_lab_uid}", 
                              params={"cluster": test_cluster}, timeout=5)
        if response.status_code == 200:
            print("✅ Get allocation successful")
            allocation_data = response.json()
            print(f"   Status: {allocation_data['allocation']['status']}")
        else:
            print(f"❌ Get allocation failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Get allocation failed: {e}")
        return False
    
    print()
    
    # Test listing allocations
    print("4️⃣  Testing list all allocations...")
    try:
        response = requests.get(f"{base_url}/allocations", timeout=5)
        if response.status_code == 200:
            print("✅ List allocations successful")
            allocations = response.json()['allocations']
            print(f"   Found {len(allocations)} active allocation(s)")
        else:
            print(f"❌ List allocations failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ List allocations failed: {e}")
        return False
    
    print()
    
    # Test stats endpoint
    print("5️⃣  Testing stats endpoint...")
    try:
        response = requests.get(f"{base_url}/stats", timeout=5)
        if response.status_code == 200:
            print("✅ Stats endpoint successful")
            stats = response.json()
            print(f"   Shared network: {stats['shared_network_cidr']}")
            print(f"   Active allocations: {stats['total_active_lab_allocations']}")
            print(f"   Total IPs available: {stats['total_ips_available']}")
            print(f"   Utilization: {stats['utilization_percent']}%")
            print(f"   Note: {stats['note']}")
        else:
            print(f"❌ Stats endpoint failed: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Stats endpoint failed: {e}")
        return False
    
    print()
    
    # Test deallocation
    print(f"6️⃣  Testing deallocation for lab_uid: {test_lab_uid} in cluster: {test_cluster}")
    try:
        response = requests.delete(
            f"{base_url}/deallocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid, "cluster": test_cluster},
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ Deallocation successful")
            print(f"   Message: {response.json()['message']}")
        else:
            print(f"❌ Deallocation failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Deallocation failed: {e}")
        return False
    
    print()
    
    # Test duplicate allocation (should fail)
    print(f"7️⃣  Testing duplicate allocation (should return existing)...")
    try:
        # Allocate again
        response1 = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid, "cluster": test_cluster},
            timeout=10
        )
        
        # Try to allocate the same lab_uid again in the same cluster
        response2 = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid, "cluster": test_cluster},
            timeout=10
        )
        
        if response2.status_code == 400:
            print("✅ Duplicate allocation properly rejected")
        else:
            print(f"❌ Duplicate allocation not handled correctly: {response2.status_code}")
            return False
        
        # Clean up
        requests.delete(
            f"{base_url}/deallocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid, "cluster": test_cluster},
            timeout=5
        )
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Duplicate allocation test failed: {e}")
        return False
    
    print()
    
    # Test overlapping IP allocation between different clusters
    print("8️⃣  Testing overlapping IP allocation between clusters...")
    try:
        cluster_a = "cluster-a"
        cluster_b = "cluster-b"
        test_lab = "overlap-test"
        
        # Allocate same lab_uid in two different clusters
        response_a = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab, "cluster": cluster_a},
            timeout=10
        )
        
        response_b = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab, "cluster": cluster_b},
            timeout=10
        )
        
        if response_a.status_code == 201 and response_b.status_code == 201:
            alloc_a = response_a.json()['env_vars']
            alloc_b = response_b.json()['env_vars']
            
            # Both should get the same IP addresses since they share the same CIDR
            worker_ip_a = alloc_a['EXTERNAL_IP_WORKER_1']
            worker_ip_b = alloc_b['EXTERNAL_IP_WORKER_1']
            
            print("✅ Overlapping allocation successful")
            print(f"   Cluster A - Worker IP: {worker_ip_a}")
            print(f"   Cluster B - Worker IP: {worker_ip_b}")
            print(f"   Same IPs across clusters: {worker_ip_a == worker_ip_b}")
            
            # Clean up both allocations
            requests.delete(f"{base_url}/deallocate", 
                          headers={"Content-Type": "application/json"},
                          json={"lab_uid": test_lab, "cluster": cluster_a}, timeout=5)
            requests.delete(f"{base_url}/deallocate",
                          headers={"Content-Type": "application/json"}, 
                          json={"lab_uid": test_lab, "cluster": cluster_b}, timeout=5)
        else:
            print(f"❌ Overlapping allocation failed: {response_a.status_code}, {response_b.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Overlapping allocation test failed: {e}")
        return False
    
    print()
    print("🎉 All tests passed successfully!")
    return True

def main():
    """Main test function"""
    base_url = os.environ.get('IPAM_URL', 'http://localhost:8080')
    
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    print("IPAM4Lab Local Test Suite")
    print("=" * 50)
    
    success = test_ipam_service(base_url)
    
    if success:
        print("\n✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

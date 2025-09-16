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
    print(f"2️⃣  Testing allocation for lab_uid: {test_lab_uid}")
    try:
        response = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid},
            timeout=10
        )
        
        if response.status_code == 201:
            print("✅ Allocation successful")
            allocation_data = response.json()
            print(f"   Lab UID: {allocation_data['lab_uid']}")
            print("   Environment Variables:")
            for key, value in allocation_data['env_vars'].items():
                print(f"     {key}={value}")
        else:
            print(f"❌ Allocation failed: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Allocation failed: {e}")
        return False
    
    print()
    
    # Test getting allocation
    print(f"3️⃣  Testing get allocation for lab_uid: {test_lab_uid}")
    try:
        response = requests.get(f"{base_url}/allocation/{test_lab_uid}", timeout=5)
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
    
    # Test deallocation
    print(f"5️⃣  Testing deallocation for lab_uid: {test_lab_uid}")
    try:
        response = requests.delete(
            f"{base_url}/deallocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid},
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
    print(f"6️⃣  Testing duplicate allocation (should return existing)...")
    try:
        # Allocate again
        response1 = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid},
            timeout=10
        )
        
        # Try to allocate the same lab_uid again
        response2 = requests.post(
            f"{base_url}/allocate",
            headers={"Content-Type": "application/json"},
            json={"lab_uid": test_lab_uid},
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
            json={"lab_uid": test_lab_uid},
            timeout=5
        )
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Duplicate allocation test failed: {e}")
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

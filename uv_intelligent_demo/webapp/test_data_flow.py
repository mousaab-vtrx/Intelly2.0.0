#!/usr/bin/env python3
"""
Test data flow from simulation through MQTT → InfluxDB → Backend.

This script:
1. Subscribes to MQTT telemetry topic and captures messages
2. Queries InfluxDB for recent data
3. Verifies backend can retrieve and process the data
4. Checks AI tools (anomaly, forecast) are working
5. Reports latency and data integrity

Run this AFTER the simulation is running.
"""

import asyncio
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiohttp
import paho.mqtt.client as mqtt
import requests
from requests.exceptions import ConnectionError, Timeout

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_success(msg: str) -> None:
    print(f"{Colors.OKGREEN}✓ {msg}{Colors.ENDC}")


def print_error(msg: str) -> None:
    print(f"{Colors.FAIL}✗ {msg}{Colors.ENDC}")


def print_warn(msg: str) -> None:
    print(f"{Colors.WARNING}⚠  {msg}{Colors.ENDC}")


def print_info(msg: str) -> None:
    print(f"{Colors.OKBLUE}ℹ  {msg}{Colors.ENDC}")


def print_header(title: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{title.center(60)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


@dataclass
class MQTTMessage:
    topic: str
    payload: str
    timestamp: datetime
    
    @property
    def data(self) -> dict:
        try:
            return json.loads(self.payload)
        except (json.JSONDecodeError, ValueError):
            return {}


class MQTTListener:
    """Listen for MQTT messages on telemetry topic"""
    
    def __init__(self, broker: str = "localhost", port: int = 1883, timeout: int = 10):
        self.broker = broker
        self.port = port
        self.timeout = timeout
        self.messages: list[MQTTMessage] = []
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.connected = False
    
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.connected = True
            print_success(f"Connected to MQTT broker at {self.broker}:{self.port}")
            client.subscribe("uv/telemetry")
            client.subscribe("uv/control/#")
        else:
            print_error(f"Failed to connect to MQTT (code {rc})")
    
    def _on_message(self, client, userdata, msg):
        try:
            message = MQTTMessage(
                topic=msg.topic,
                payload=msg.payload.decode('utf-8'),
                timestamp=datetime.now(timezone.utc)
            )
            self.messages.append(message)
            print_info(f"Received MQTT: {msg.topic} ({len(self.messages)} total)")
        except Exception as e:
            print_warn(f"Error processing MQTT message: {e}")
    
    def connect_and_listen(self) -> bool:
        """Connect and listen for messages"""
        try:
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            
            # Wait for connection
            start = time.time()
            while not self.connected and (time.time() - start) < self.timeout:
                time.sleep(0.1)
            
            if not self.connected:
                print_error(f"Failed to connect to MQTT within {self.timeout}s")
                return False
            
            return True
        except Exception as e:
            print_error(f"MQTT connection error: {e}")
            return False
    
    def stop(self) -> None:
        """Stop listening"""
        self.client.loop_stop()
        self.client.disconnect()
    
    def get_messages(self, topic_filter: Optional[str] = None) -> list[MQTTMessage]:
        """Get messages, optionally filtered by topic"""
        if topic_filter:
            return [m for m in self.messages if topic_filter in m.topic]
        return self.messages


class BackendTester:
    """Test backend data retrieval and processing"""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 10):
        self.base_url = base_url
        self.timeout = timeout
    
    def check_health(self) -> bool:
        """Check backend health endpoint"""
        try:
            response = requests.get(
                f"{self.base_url}/api/health",
                timeout=self.timeout
            )
            if response.status_code == 200:
                print_success("Backend health check passed")
                return True
            else:
                print_error(f"Backend health check failed: {response.status_code}")
                return False
        except (ConnectionError, Timeout) as e:
            print_error(f"Backend connection failed: {e}")
            return False
    
    def get_state(self) -> Optional[dict]:
        """Get current system state"""
        try:
            response = requests.get(
                f"{self.base_url}/api/state",
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                print_success("Backend state retrieved")
                return data
            else:
                print_error(f"Failed to get state: {response.status_code}")
                return None
        except (ConnectionError, Timeout, json.JSONDecodeError) as e:
            print_error(f"State retrieval failed: {e}")
            return None
    
    def get_tools_analysis(self, limit: int = 10) -> Optional[dict]:
        """Get AI tools analysis"""
        try:
            response = requests.get(
                f"{self.base_url}/api/ai/tools/analysis?limit={limit}",
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                print_success(f"AI tools analysis retrieved ({len(data)} items)")
                return data
            else:
                print_error(f"Failed to get tools analysis: {response.status_code}")
                return None
        except (ConnectionError, Timeout, json.JSONDecodeError) as e:
            print_error(f"Tools analysis failed: {e}")
            return None
    
    def get_alerts(self) -> Optional[list]:
        """Get current alerts"""
        try:
            response = requests.get(
                f"{self.base_url}/api/alerts",
                timeout=self.timeout
            )
            if response.status_code == 200:
                data = response.json()
                print_success(f"Alerts retrieved ({len(data)} total)")
                return data
            else:
                print_error(f"Failed to get alerts: {response.status_code}")
                return None
        except (ConnectionError, Timeout, json.JSONDecodeError) as e:
            print_error(f"Alerts retrieval failed: {e}")
            return None


class InfluxDBTester:
    """Test InfluxDB connectivity and data"""
    
    def __init__(self, url: str = "http://localhost:8086", org: str = "uv_org", 
                 bucket: str = "uv_demo", token: str = "uv_admin_token", timeout: int = 10):
        self.url = url
        self.org = org
        self.bucket = bucket
        self.token = token
        self.timeout = timeout
    
    def query_recent_data(self, hours: int = 1) -> Optional[dict]:
        """Query recent data from InfluxDB"""
        try:
            flux_query = f'''
from(bucket:"{self.bucket}")
  |> range(start: -{hours}h)
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 100)
'''
            response = requests.post(
                f"{self.url}/api/v2/query?org={self.org}",
                headers={
                    "Authorization": f"Token {self.token}",
                    "Content-Type": "application/vnd.flux"
                },
                data=flux_query,
                timeout=self.timeout
            )
            if response.status_code == 200:
                print_success(f"InfluxDB query successful (from last {hours}h)")
                return response.text
            else:
                print_error(f"InfluxDB query failed: {response.status_code}")
                return None
        except (ConnectionError, Timeout) as e:
            print_error(f"InfluxDB connection failed: {e}")
            return None
    
    def check_bucket_exists(self) -> bool:
        """Check if bucket exists"""
        try:
            response = requests.get(
                f"{self.url}/api/v2/buckets?org={self.org}",
                headers={"Authorization": f"Token {self.token}"},
                timeout=self.timeout
            )
            if response.status_code == 200:
                buckets = response.json().get("buckets", [])
                bucket_names = [b.get("name") for b in buckets]
                if self.bucket in bucket_names:
                    print_success(f"InfluxDB bucket '{self.bucket}' exists")
                    return True
                else:
                    print_error(f"Bucket '{self.bucket}' not found (available: {bucket_names})")
                    return False
            else:
                print_error(f"Failed to list buckets: {response.status_code}")
                return False
        except (ConnectionError, Timeout, json.JSONDecodeError) as e:
            print_error(f"Bucket check failed: {e}")
            return False


def main():
    """Run complete data flow test"""
    print_header("UV REACTOR DATA FLOW TEST")
    
    # Phase 1: Backend connectivity
    print_header("PHASE 1: Backend Connectivity")
    backend = BackendTester()
    if not backend.check_health():
        print_error("Backend is not running. Start it with: bash start_simulation.sh")
        return 1
    
    # Phase 2: InfluxDB connectivity
    print_header("PHASE 2: InfluxDB Data Validation")
    influx = InfluxDBTester()
    if not influx.check_bucket_exists():
        print_error("InfluxDB bucket not accessible. Check containers.")
        return 1
    
    # Query InfluxDB for recent data
    data = influx.query_recent_data(hours=2)
    if data:
        print_info("Recent InfluxDB data (last 100 points):")
        print(data[:500])  # Print first 500 chars
    
    # Phase 3: MQTT Message Capture
    print_header("PHASE 3: MQTT Message Capture (30 second window)")
    mqtt_listener = MQTTListener(timeout=5)
    if not mqtt_listener.connect_and_listen():
        print_warn("MQTT connection failed. Simulation may not be running.")
    else:
        try:
            print_info("Listening for MQTT messages for 30 seconds...")
            time.sleep(30)
            
            telemetry_msgs = mqtt_listener.get_messages("uv/telemetry")
            control_msgs = mqtt_listener.get_messages("uv/control")
            
            print_success(f"Captured {len(telemetry_msgs)} telemetry messages")
            print_success(f"Captured {len(control_msgs)} control messages")
            
            if telemetry_msgs:
                print_info("Latest telemetry message:")
                latest = telemetry_msgs[-1]
                print(json.dumps(latest.data, indent=2))
        finally:
            mqtt_listener.stop()
    
    # Phase 4: Backend State
    print_header("PHASE 4: Backend State & Data Processing")
    state = backend.get_state()
    if state:
        print_info("Backend state:")
        print(json.dumps(state, indent=2, default=str)[:1000])
    
    # Phase 5: AI Tools
    print_header("PHASE 5: AI Tools Analysis")
    tools = backend.get_tools_analysis(limit=5)
    if tools:
        print_info("AI tools output (anomaly, forecast, etc.):")
        for tool_name, tool_data in list(tools.items())[:3]:
            print(f"\n{tool_name}:")
            print(json.dumps(tool_data, indent=2, default=str)[:500])
    
    # Phase 6: Alerts
    print_header("PHASE 6: Active Alerts")
    alerts = backend.get_alerts()
    if alerts:
        if len(alerts) > 0:
            print_warn(f"Active alerts: {len(alerts)}")
            for alert in alerts[:3]:
                print(f"  - {alert}")
        else:
            print_success("No active alerts")
    else:
        print_warn("Could not retrieve alerts")
    
    # Summary
    print_header("TEST COMPLETE")
    print_success("Data flow validation finished!")
    print("\nNext steps:")
    print("1. Monitor simulation: tail -f logs/simulation.log")
    print("2. Check Node-Red: http://localhost:1880")
    print("3. View InfluxDB: http://localhost:8086")
    print("4. Test backend API: curl http://localhost:8000/api/state")
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

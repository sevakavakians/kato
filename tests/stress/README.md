# KATO Stress Test Suite

## Overview

The KATO Stress Test Suite is a comprehensive performance testing framework designed to evaluate KATO's behavior under various load conditions. It simulates real-world usage patterns and identifies performance bottlenecks, memory leaks, and stability issues.

## Quick Start

### Basic Usage

```bash
# Run all stress tests
./run_stress_tests.sh

# Run specific test
./run_stress_tests.sh --test concurrent

# Run quick tests (reduced duration)
./run_stress_tests.sh --quick

# Run with heavy load profile
./run_stress_tests.sh --test sustained --profile heavy
```

### Python Direct Usage

```bash
# Run all tests
python3 test_stress_performance.py

# Run specific test
python3 test_stress_performance.py --test burst

# Use custom config
python3 test_stress_performance.py --config custom_config.yaml
```

## Test Scenarios

### 1. Concurrent Requests Test
Tests KATO's ability to handle multiple simultaneous users.

**What it tests:**
- Thread safety
- Connection handling
- Request queuing
- Resource contention

**Key metrics:**
- Response time under load
- Error rate
- Throughput (requests/second)

### 2. Sustained Load Test
Evaluates performance under continuous load over extended periods.

**Load profiles:**
- **Light**: 10 users, 60 seconds
- **Moderate**: 50 users, 5 minutes
- **Heavy**: 200 users, 10 minutes
- **Extreme**: 500 users, 5 minutes
- **Endurance**: 25 users, 1 hour

**What it tests:**
- Performance degradation over time
- Memory leaks
- Resource exhaustion
- Stability

### 3. Burst Traffic Test
Simulates sudden spikes in traffic.

**What it tests:**
- Queue handling
- Recovery time
- Peak capacity
- Error handling under stress

**Default configuration:**
- 1000 requests per burst
- 100ms burst duration
- 5 bursts with 10-second intervals

### 4. Connection Pool Exhaustion Test
Tests behavior when connection limits are reached.

**What it tests:**
- Connection pool management
- Queue overflow handling
- Graceful degradation
- Recovery mechanisms

### 5. Memory Leak Test
Long-running test to detect memory leaks.

**What it tests:**
- Memory growth over time
- Garbage collection effectiveness
- Resource cleanup
- Long-term stability

**Duration:** 10 minutes by default

### 6. Error Recovery Test
Evaluates system resilience and recovery from errors.

**Test phases:**
1. Establish baseline performance
2. Induce errors with invalid requests
3. Monitor recovery to baseline

**What it tests:**
- Error handling
- Circuit breaker behavior
- Recovery time
- System resilience

## Configuration

### Main Configuration File: `stress_config.yaml`

The configuration file controls all aspects of stress testing:

#### Load Profiles
```yaml
load_profiles:
  moderate:
    concurrent_users: 50
    duration_seconds: 300
    ramp_up_seconds: 30
    requests_per_user_per_second: 2
    think_time_ms: 500
```

#### Test Parameters
```yaml
test_parameters:
  connection_timeout_seconds: 30
  request_timeout_seconds: 10
  max_retries: 3
  connection_pool_size: 100
```

#### Operations Mix
```yaml
operations_mix:
  observe: 0.60      # 60% observe operations
  learn: 0.10        # 10% learn operations
  predictions: 0.20  # 20% get predictions
  short_term_memory: 0.05  # 5% short-term memory queries
  clear_memory: 0.05    # 5% memory clear operations
```

#### Performance Thresholds
```yaml
performance_thresholds:
  response_time_p99_max: 100  # milliseconds
  max_error_rate: 0.001  # 0.1%
  max_memory_usage_mb: 2000
  max_cpu_usage_percent: 80
```

## Performance Metrics

### Response Time Metrics
- **P50 (Median)**: Response time at 50th percentile
- **P95**: Response time at 95th percentile
- **P99**: Response time at 99th percentile
- **P99.9**: Response time at 99.9th percentile

### Throughput Metrics
- **RPS**: Requests per second
- **Success rate**: Percentage of successful requests
- **Error rate**: Percentage of failed requests

### Resource Metrics
- **CPU usage**: Percentage and trends
- **Memory usage**: MB and percentage
- **Network I/O**: Bytes sent/received
- **Active connections**: Number of concurrent connections

### Operation-Specific Metrics
- Per-operation response times
- Per-operation success rates
- Operation distribution analysis

## Results and Reporting

### Output Directory
Results are saved in `./stress_test_results/` with timestamps.

### File Formats

#### JSON Results
```json
{
  "concurrent_requests": {
    "status": "completed",
    "results": {
      "total_requests": 5000,
      "error_rate": 0.002,
      "response_time_p99": 45.2,
      "throughput_rps": 83.3
    }
  }
}
```

#### CSV Metrics
- `metrics_TIMESTAMP_performance.csv`: Request-level metrics
- `metrics_TIMESTAMP_resources.csv`: Resource usage over time

### Console Output
```
============================================
STRESS TEST SUMMARY
============================================

concurrent_requests:
  Status: completed
  Total Requests: 5,000
  Success Rate: 99.80%
  P99 Response Time: 45.2ms
  Throughput: 83.3 req/s

Threshold Violations:
  ⚠️  heavy_load: P99 response time (156.3ms) exceeds threshold (100ms)

✅ Most performance thresholds met!
```

## Best Practices

### 1. Environment Preparation
- Ensure KATO is running with a clean state
- Check available system resources
- Close unnecessary applications
- Use consistent hardware/environment for comparisons

### 2. Test Isolation
- Run tests individually for accurate measurements
- Allow cooldown periods between tests
- Clear memory between test runs
- Monitor background processes

### 3. Realistic Load Patterns
- Use operation mixes that reflect real usage
- Include think time between requests
- Simulate gradual ramp-up periods
- Test both normal and peak conditions

### 4. Monitoring
- Watch for warning signs during tests:
  - Increasing response times
  - Growing error rates
  - Memory growth
  - CPU saturation
- Use container monitoring for Docker deployments
- Check logs for errors and warnings

### 5. Analysis
- Compare results against baselines
- Look for trends, not just absolute numbers
- Consider percentiles, not just averages
- Investigate anomalies and outliers

## Troubleshooting

### Common Issues

#### 1. Connection Refused
```
Error: Connection refused at http://localhost:8000
```
**Solution:** Ensure KATO is running: `./kato-manager.sh start`

#### 2. High Error Rate
```
Error rate: 15.30% (threshold: 0.10%)
```
**Causes:**
- System overloaded
- Insufficient resources
- Configuration issues

**Solutions:**
- Reduce concurrent users
- Increase timeouts
- Check system resources

#### 3. Memory Issues
```
Warning: Low available memory: 512MB
```
**Solution:** Free up memory or reduce test load

#### 4. Timeout Errors
```
Error: Request timeout after 10 seconds
```
**Solutions:**
- Increase timeout in config
- Reduce load
- Check KATO performance

### Debug Mode

Enable verbose logging:
```bash
./run_stress_tests.sh --verbose
```

Check container logs:
```bash
docker logs kato-stress-test --tail 100
```

Monitor in real-time:
```bash
docker stats kato-stress-test
```

## Advanced Usage

### Custom Test Scenarios

Create custom test by extending `StressTestRunner`:

```python
from test_stress_performance import StressTestRunner

class CustomStressTest(StressTestRunner):
    def test_custom_scenario(self):
        """Custom test implementation."""
        self.monitor.start()
        
        # Your test logic here
        for i in range(100):
            self._make_request("observe", {"strings": ["test"]})
            
        self.monitor.stop()
        return self.monitor.get_current_statistics()

# Run custom test
runner = CustomStressTest()
runner.setup()
runner.test_custom_scenario()
runner.teardown()
```

### Custom Load Patterns

Implement custom load patterns:

```python
from load_generator import LoadPattern, LoadProfile

# Define custom pattern
class CustomPattern(LoadPattern):
    CUSTOM = "custom"

# Use in profile
profile = LoadProfile(
    pattern=CustomPattern.CUSTOM,
    duration_seconds=300,
    initial_users=10,
    peak_users=100,
    requests_per_user_per_second=3.0
)
```

### Custom Metrics Collection

Add custom metrics:

```python
from performance_monitor import PerformanceMonitor

monitor = PerformanceMonitor()

# Add custom alert
monitor.alert_thresholds['custom_metric'] = 100

# Record custom metric
monitor.record_request(
    response_time_ms=25.5,
    success=True,
    operation_type="custom_operation"
)
```

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Stress Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  stress-test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Setup Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.9'
        
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        
    - name: Start KATO
      run: |
        ./kato-manager.sh build
        ./kato-manager.sh start
        
    - name: Run stress tests
      run: |
        cd tests/stress
        ./run_stress_tests.sh --quick
        
    - name: Upload results
      uses: actions/upload-artifact@v2
      with:
        name: stress-test-results
        path: tests/stress/stress_test_results/
        
    - name: Check thresholds
      run: |
        python3 -c "
        import json
        with open('tests/stress/stress_test_results/latest.json') as f:
            results = json.load(f)
            # Check if tests passed thresholds
            # Exit with error if thresholds violated
        "
```

### Jenkins Pipeline Example

```groovy
pipeline {
    agent any
    
    stages {
        stage('Setup') {
            steps {
                sh './kato-manager.sh start'
            }
        }
        
        stage('Stress Test') {
            steps {
                sh 'cd tests/stress && ./run_stress_tests.sh --test sustained --profile moderate'
            }
        }
        
        stage('Analyze Results') {
            steps {
                publishHTML([
                    reportDir: 'tests/stress/stress_test_results',
                    reportFiles: '*.html',
                    reportName: 'Stress Test Report'
                ])
            }
        }
    }
    
    post {
        always {
            sh './kato-manager.sh stop'
        }
    }
}
```

## Performance Tuning

Based on stress test results, consider these optimizations:

### 1. Connection Pool Tuning
```yaml
connection_pool_size: 200  # Increase for high concurrency
connection_pool_overflow: 100
connection_reuse: true
```

### 2. Timeout Adjustments
```yaml
connection_timeout_seconds: 45  # Increase for slow networks
request_timeout_seconds: 20     # Increase for complex operations
```

### 3. Rate Limiting
```yaml
max_requests_per_second: 5000  # Adjust based on capacity
rate_limit_burst_size: 500
```

### 4. Resource Limits
```yaml
max_memory_usage_mb: 4096  # Increase for large datasets
max_cpu_usage_percent: 90  # Allow higher CPU usage
```

## Contributing

To add new stress tests:

1. Create test method in `test_stress_performance.py`
2. Add configuration in `stress_config.yaml`
3. Update documentation
4. Submit pull request with results

## License

See main KATO repository for license information.
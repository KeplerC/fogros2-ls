std_msgs/String identity 
# help with network analysis 
std_msgs/String ip_addr
# help with compute analysis 
int16 num_cpu_core
float64 cpu_frequency 
float64 cpu_usage 0         
bool has_gpu False 
# runtime stats 
float64 min_latency -1.0
float64 max_latency -1.0
float64 mean_latency -1.0
float64 median_latency -1.0
float64 std_latency -1.0
float64 max_kmeans_latency -1.0
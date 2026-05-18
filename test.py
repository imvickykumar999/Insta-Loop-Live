# Get API Key from https://dashboard.uptimerobot.com/integrations

import requests

def get_detailed_status():
    url = "https://api.uptimerobot.com/v2/getMonitors"
    
    # We added custom_uptime_ratios=1-7-30 and response_times flags to get the dashboard data
    payload = "api_key=m802831286-0a1cff2408c2fb3dfbab3322&format=json&logs=1&custom_uptime_ratios=1-7-30&response_times=1&response_times_limit=5"
    headers = {
        'content-type': "application/x-www-form-urlencoded",
        'cache-control': "no-cache"
    }

    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        if 'monitors' in data and len(data['monitors']) > 0:
            monitor = data['monitors'][0]
            
            # 1. Map the status code to a readable string
            status_map = {0: "Paused", 1: "Not Checked Yet", 2: "Up", 8: "Seems Down", 9: "Down"}
            current_status = status_map.get(monitor['status'], "Unknown")
            
            # 2. Extract the custom uptime ratios (24h, 7d, 30d)
            ratios = monitor.get('custom_uptime_ratio', 'N/A-N/A-N/A').split('-')
            uptime_24h = ratios[0] if len(ratios) > 0 else 'N/A'
            uptime_7d = ratios[1] if len(ratios) > 1 else 'N/A'
            uptime_30d = ratios[2] if len(ratios) > 2 else 'N/A'

            # 3. Calculate the average response time from the latest pings
            response_times = monitor.get('response_times', [])
            if response_times:
                avg_ping = sum(int(rt['value']) for rt in response_times) // len(response_times)
            else:
                avg_ping = "N/A"

            # 4. Find the latest incident from the logs (Type 1 = Down)
            logs = monitor.get('logs', [])
            latest_incident = "No recent incidents"
            for log in logs:
                if log['type'] == 1:
                    duration_mins = log.get('duration', 0) // 60
                    latest_incident = f"Down for {duration_mins} minutes"
                    break # Stop after finding the most recent downtime

            # Print the formatted dashboard
            print(f"--- Dashboard for {monitor['friendly_name']} ---")
            print(f"Current Status:  {current_status}")
            print(f"Uptime (24h):    {uptime_24h}%")
            print(f"Uptime (7d):     {uptime_7d}%")
            print(f"Uptime (30d):    {uptime_30d}%")
            print(f"Recent Ping Avg: {avg_ping} ms")
            print(f"Latest Incident: {latest_incident}")
            print("------------------------------------------")
            
        else:
            print("No monitor data found.")
    else:
        print(f"API Request Failed: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    get_detailed_status()

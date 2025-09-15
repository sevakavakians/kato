#!/bin/bash
# Port discovery script for KATO with dynamic ports
# Discovers and saves dynamically assigned ports to JSON file

set -e

# Configuration
PORTS_FILE=".kato-ports.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to get container port
get_container_port() {
    local container_name=$1
    local internal_port=$2
    
    # Get the mapped port using docker port command
    port_info=$(docker port "$container_name" "$internal_port" 2>/dev/null || echo "")
    
    if [ -z "$port_info" ]; then
        echo ""
        return 1
    fi
    
    # Extract just the port number (format is 0.0.0.0:PORT or [::]:PORT)
    echo "$port_info" | head -1 | sed 's/.*://'
}

# Function to check if container is running
is_container_running() {
    local container_name=$1
    docker ps --format "{{.Names}}" | grep -q "^${container_name}$"
}

# Main discovery function
discover_ports() {
    echo -e "${BLUE}[INFO]${NC} Discovering KATO service ports..."
    
    # Initialize JSON structure
    json_output='{'
    json_output+='"timestamp":"'$(date -u +"%Y-%m-%dT%H:%M:%SZ")'",'
    json_output+='"services":{'
    
    # Discover KATO service ports
    services=("kato-primary-v2:8000:primary" "kato-testing-v2:8000:testing" "kato-analytics-v2:8000:analytics")
    first=true
    
    for service in "${services[@]}"; do
        IFS=':' read -r container internal label <<< "$service"
        
        if is_container_running "$container"; then
            port=$(get_container_port "$container" "$internal")
            if [ -n "$port" ]; then
                if [ "$first" = false ]; then
                    json_output+=','
                fi
                json_output+='"'$label'":{"container":"'$container'","port":'$port',"url":"http://localhost:'$port'"}'
                echo -e "${GREEN}✓${NC} $label KATO: http://localhost:$port"
                first=false
            else
                echo -e "${YELLOW}⚠${NC} $label KATO: Container running but port not mapped"
            fi
        else
            echo -e "${RED}✗${NC} $label KATO: Container not running"
        fi
    done
    
    json_output+='},'
    
    # Discover database ports
    json_output+='"databases":{'
    
    databases=("kato-mongodb-v2:27017:mongodb" "kato-qdrant-v2:6333:qdrant" "kato-redis-v2:6379:redis")
    first=true
    
    for database in "${databases[@]}"; do
        IFS=':' read -r container internal label <<< "$database"
        
        if is_container_running "$container"; then
            port=$(get_container_port "$container" "$internal")
            if [ -n "$port" ]; then
                if [ "$first" = false ]; then
                    json_output+=','
                fi
                json_output+='"'$label'":{"container":"'$container'","port":'$port',"url":"'
                
                # Format URL based on service type
                case $label in
                    mongodb)
                        json_output+='mongodb://localhost:'$port'"}'
                        echo -e "${GREEN}✓${NC} MongoDB: mongodb://localhost:$port"
                        ;;
                    qdrant)
                        json_output+='http://localhost:'$port'"}'
                        echo -e "${GREEN}✓${NC} Qdrant: http://localhost:$port"
                        ;;
                    redis)
                        json_output+='redis://localhost:'$port'"}'
                        echo -e "${GREEN}✓${NC} Redis: redis://localhost:$port"
                        ;;
                esac
                first=false
            else
                echo -e "${YELLOW}⚠${NC} $label: Container running but port not mapped"
            fi
        else
            echo -e "${RED}✗${NC} $label: Container not running"
        fi
    done
    
    json_output+='}}'
    
    # Save to file
    echo "$json_output" | python -m json.tool > "$PORTS_FILE" 2>/dev/null || echo "$json_output" > "$PORTS_FILE"
    
    echo -e "\n${BLUE}[INFO]${NC} Port mappings saved to ${PORTS_FILE}"
}

# Function to display saved ports
show_saved_ports() {
    if [ -f "$PORTS_FILE" ]; then
        echo -e "\n${BLUE}[INFO]${NC} Current port mappings from ${PORTS_FILE}:"
        
        # Use Python to parse and display JSON nicely
        python3 -c "
import json
import sys

try:
    with open('$PORTS_FILE', 'r') as f:
        data = json.load(f)
    
    print('\nKATO Services:')
    for name, info in data.get('services', {}).items():
        print(f'  {name.capitalize()}: {info[\"url\"]}')
    
    print('\nDatabases:')
    for name, info in data.get('databases', {}).items():
        print(f'  {name.capitalize()}: {info[\"url\"]}')
    
    print(f'\nLast updated: {data.get(\"timestamp\", \"Unknown\")}')
except Exception as e:
    print(f'Error reading ports file: {e}', file=sys.stderr)
    sys.exit(1)
"
    else
        echo -e "${YELLOW}[WARNING]${NC} No saved port mappings found. Run discovery first."
        return 1
    fi
}

# Function to export ports as environment variables
export_ports_env() {
    if [ -f "$PORTS_FILE" ]; then
        # Use Python to parse JSON and output export commands
        python3 -c "
import json

with open('$PORTS_FILE', 'r') as f:
    data = json.load(f)

# Export KATO service ports
for name, info in data.get('services', {}).items():
    var_name = f'KATO_{name.upper()}_PORT'
    print(f'export {var_name}={info[\"port\"]}')
    var_name = f'KATO_{name.upper()}_URL'
    print(f'export {var_name}=\"{info[\"url\"]}\"')

# Export database ports
for name, info in data.get('databases', {}).items():
    var_name = f'{name.upper()}_PORT'
    print(f'export {var_name}={info[\"port\"]}')
    var_name = f'{name.upper()}_URL'
    print(f'export {var_name}=\"{info[\"url\"]}\"')
"
        echo -e "\n${GREEN}[SUCCESS]${NC} Environment variables exported. Use 'source <(./discover-ports.sh export)' to apply."
    else
        echo -e "${RED}[ERROR]${NC} No saved port mappings found. Run discovery first."
        return 1
    fi
}

# Main script logic
case "${1:-discover}" in
    discover)
        discover_ports
        ;;
    show)
        show_saved_ports
        ;;
    export)
        export_ports_env
        ;;
    json)
        if [ -f "$PORTS_FILE" ]; then
            cat "$PORTS_FILE"
        else
            echo "{\"error\": \"No port mappings found\"}"
            exit 1
        fi
        ;;
    help|--help|-h)
        echo "KATO Dynamic Port Discovery Tool"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  discover  - Discover and save current port mappings (default)"
        echo "  show      - Display saved port mappings"
        echo "  export    - Output environment variable exports"
        echo "  json      - Output raw JSON data"
        echo "  help      - Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                    # Discover ports"
        echo "  $0 show               # Show saved ports"
        echo "  source <($0 export)   # Export as environment variables"
        ;;
    *)
        echo -e "${RED}[ERROR]${NC} Unknown command: $1"
        echo "Use '$0 help' for usage information"
        exit 1
        ;;
esac
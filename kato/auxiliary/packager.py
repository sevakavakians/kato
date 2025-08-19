import json

def pack(data):
    return json.dumps(data)

def unpack(data):
    return json.loads(data)


def notify_amazon(event_type, payload):
    return {
        "event_type": event_type,
        "payload": payload,
    }

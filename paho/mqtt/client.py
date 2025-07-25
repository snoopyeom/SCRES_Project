class Client:
    def __init__(self, *args, **kwargs):
        self.on_message = None
    def connect(self, host, port=1883, keepalive=60):
        pass
    def subscribe(self, topic):
        pass
    def loop_start(self):
        pass
    def loop_forever(self):
        pass
    def publish(self, topic, payload=None, qos=0, retain=False):
        pass

class CommandDispatcher:
    def queue(self, channel, seqnum, payload):
        raise NotImplementedError("Database-backed outbound command storage is not configured in the slimmed-down schema.")

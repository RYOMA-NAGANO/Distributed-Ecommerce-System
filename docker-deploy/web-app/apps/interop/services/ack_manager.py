class SeqNumAllocator:
    def next_for_channel(self, channel):
        raise NotImplementedError("Database-backed seqnum allocation is not configured in the slimmed-down schema.")

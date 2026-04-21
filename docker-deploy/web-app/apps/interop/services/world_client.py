import json

from django.conf import settings

from protos import world_ups_pb2


def build_connect_message():
    connect = world_ups_pb2.UConnect()
    if settings.WORLD_ID:
        connect.worldid = int(settings.WORLD_ID)
    connect.isAmazon = False

    for truck in json.loads(settings.UPS_TRUCKS):
        init_truck = connect.trucks.add()
        init_truck.id = truck["id"]
        init_truck.x = truck["x"]
        init_truck.y = truck["y"]

    return connect

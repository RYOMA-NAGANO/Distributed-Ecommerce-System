from rest_framework import serializers

from apps.core.models import Package
from apps.core.services import NoAvailableTruckError, create_package_with_assigned_truck


class AmazonPackageCreateSerializer(serializers.Serializer):
    shipment_id = serializers.CharField(max_length=100)
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    dest_x = serializers.IntegerField()
    dest_y = serializers.IntegerField()
    warehouse_id = serializers.IntegerField(default=0)
    world_package_id = serializers.IntegerField(required=False, allow_null=True, default=None)

    def create(self, validated_data):
        try:
            return create_package_with_assigned_truck(
                shipment_id=validated_data["shipment_id"],
                username=validated_data["username"],
                dest_x=validated_data["dest_x"],
                dest_y=validated_data["dest_y"],
                email=validated_data.get("email") or "",
                warehouse_id=validated_data.get("warehouse_id", 0),
                world_package_id=validated_data.get("world_package_id"),
            )
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        except NoAvailableTruckError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AmazonPackageResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = [
            "shipment_id",
            "warehouse_id",
            "world_package_id",
            "dest_x",
            "dest_y",
            "status",
            "truck_id",
        ]

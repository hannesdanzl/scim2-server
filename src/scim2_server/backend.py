from typing import Union

from scim2_models import BaseModel
from scim2_models import Extension
from scim2_models import Resource
from scim2_models import ResourceType
from scim2_models import Schema
from scim2_models import SearchRequest

class Backend:
    """The base class for a SCIM provider backend."""

    def __init__(self):
        self.schemas: dict[str, Schema] = {}
        self.resource_types: dict[str, ResourceType] = {}
        self.resource_types_by_endpoint: dict[str, ResourceType] = {}
        self.models_dict: dict[str, BaseModel] = {}

    def __enter__(self):
        """Allow the backend to be used as a context manager.

        This enables support for transactions.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the transaction."""
        pass

    def register_schema(self, schema: Schema):
        """Register a Schema for use with the backend."""
        self.schemas[schema.id] = schema

    def get_schemas(self):
        """Return all schemas registered with the backend."""
        return self.schemas.values()

    def get_schema(self, schema_id: str) -> Schema | None:
        """Get a schema by its id."""
        return self.schemas.get(schema_id)

    def register_resource_type(self, resource_type: ResourceType):
        """Register a ResourceType for use with the backend.

        The schemas used for the resource and its extensions must have
        been registered with the Backend beforehand.
        """
        if resource_type.schema_ not in self.schemas:
            raise RuntimeError(f"Unknown schema: {resource_type.schema_}")
        for resource_extension in resource_type.schema_extensions or []:
            if resource_extension.schema_ not in self.schemas:
                raise RuntimeError(f"Unknown schema: {resource_extension.schema_}")

        self.resource_types[resource_type.id] = resource_type
        self.resource_types_by_endpoint[resource_type.endpoint.lower()] = resource_type

        extensions = [
            Extension.from_schema(self.get_schema(se.schema_))
            for se in resource_type.schema_extensions or []
        ]
        base_schema = self.get_schema(resource_type.schema_)
        self.models_dict[resource_type.id] = Resource.from_schema(base_schema)
        if extensions:
            self.models_dict[resource_type.id] = self.models_dict[resource_type.id][
                Union[tuple(extensions)]  # noqa: UP007
            ]

    def get_resource_types(self):
        """Return all resource types registered with the backend."""
        return self.resource_types.values()

    def get_resource_type(self, resource_type_id: str) -> ResourceType | None:
        """Return the resource type by its id."""
        return self.resource_types.get(resource_type_id)

    def get_resource_type_by_endpoint(self, endpoint: str) -> ResourceType | None:
        """Return the resource type by its endpoint."""
        return self.resource_types_by_endpoint.get(endpoint.lower())

    def get_model(self, resource_type_id: str) -> BaseModel | None:
        """Return the Pydantic Python model for a given resource type."""
        return self.models_dict.get(resource_type_id)

    def get_models(self):
        """Return all Pydantic Python models for all known resource types."""
        return self.models_dict.values()

    def query_resources(
        self,
        tenant_id: str, 
        search_request: SearchRequest,
        resource_type_id: str | None = None,
    ) -> tuple[int, list[Resource]]:
        """Query the backend for a set of resources.

        :param search_request: SearchRequest instance describing the
            query.
        :param resource_type_id: ID of the resource type to query. If
            None, all resource types are queried.
        :return: A tuple of "total results" and a List of found
            Resources. The List must contain a copy of resources.
            Mutating elements in the List must not modify the data
            stored in the backend.
        :raises SCIMException: If the backend only supports querying for
            one resource type at a time, setting resource_type_id to
            None the backend may raise a
            SCIMException(Error.make_too_many_error()).
        """
        raise NotImplementedError

    def get_resource(self, tenant_id: str, resource_type_id: str, object_id: str) -> Resource | None:
        """Query the backend for a resources by its ID.

        :param resource_type_id: ID of the resource type to get the
            object from.
        :param object_id: ID of the object to get.
        :return: The resource object if it exists, None otherwise. The
            resource must be a copy, modifying it must not change the
            data stored in the backend.
        """
        raise NotImplementedError

    def delete_resource(self, tenant_id: str, resource_type_id: str, object_id: str) -> bool:
        """Delete a resource.

        :param resource_type_id: ID of the resource type to delete the
            object from.
        :param object_id: ID of the object to delete.
        :return: True if the resource was deleted, False otherwise.
        """
        raise NotImplementedError

    def create_resource(
        self, tenant_id: str, resource_type_id: str, resource: Resource
    ) -> Resource | None:
        """Create a resource.

        :param resource_type_id: ID of the resource type to create.
        :param resource: Resource to create.
        :return: The created resource. Creation should set system-
            defined attributes (ID, Metadata). May be the same object
            that is passed in.
        """
        raise NotImplementedError

    def update_resource(
        self, tenant_id: str, resource_type_id: str, resource: Resource
    ) -> Resource | None:
        """Update a resource. The resource is identified by its ID.

        :param resource_type_id: ID of the resource type to update.
        :param resource: Resource to update.
        :return: The updated resource. Updating should update the
            "meta.lastModified" data. May be the same object that is
            passed in.
        """
        raise NotImplementedError

import dataclasses
import datetime
import operator
import pickle
import uuid
from threading import Lock

from scim2_filter_parser import lexer
from scim2_filter_parser.parser import SCIMParser
from scim2_models import Attribute
from scim2_models import CaseExact
from scim2_models import Error
from scim2_models import Meta
from scim2_models import Resource
from scim2_models import ResourceType
from scim2_models import Schema
from scim2_models import SearchRequest
from scim2_models import Uniqueness
from werkzeug.http import generate_etag

from scim2_server.filter import evaluate_filter
from scim2_server.operators import ResolveSortOperator
from scim2_server.utils import SCIMException
from scim2_server.utils import get_by_alias
from scim2_server.backend import Backend


class InMemoryBackend(Backend):
    """An example in-memory backend for the SCIM provider.

    It is not optimized for performance. Many operations are O(n) or
    worse, whereas they would perform better with an actual production
    database in the backend. This is intentional to keep the
    implementation simple.
    """

    @dataclasses.dataclass
    class UniquenessDescriptor:
        """Used to mimic uniqueness constraints e.g. from a SQL database."""

        schema: str | None
        attribute_name: str
        case_exact: bool

        def get_attribute(self, resource: Resource):
            if self.schema is not None:
                resource = getattr(resource, get_by_alias(resource, self.schema))
            result = getattr(resource, get_by_alias(resource, self.attribute_name))
            if not self.case_exact:
                result = result.lower()
            return result

    @classmethod
    def collect_unique_attrs(
        cls, attributes: list[Attribute], schema: str | None
    ) -> list[UniquenessDescriptor]:
        ret = []
        for attr in attributes:
            if attr.uniqueness != Uniqueness.none:
                ret.append(
                    cls.UniquenessDescriptor(
                        schema, attr.name, attr.case_exact == CaseExact.true
                    )
                )
        return ret

    @classmethod
    def collect_resource_unique_attrs(
        cls, resource_type: ResourceType, schemas: dict[str, Schema]
    ) -> list[list[UniquenessDescriptor]]:
        ret = cls.collect_unique_attrs(schemas[resource_type.schema_].attributes, None)
        for extension in resource_type.schema_extensions or []:
            ret.extend(
                InMemoryBackend.collect_unique_attrs(
                    schemas[extension.schema_].attributes, extension.schema_
                )
            )
        return ret
    
    def __init__(self):
        super().__init__()
        self.resources: dict[str, list[Resource]] = {}
        self.unique_attributes: dict[str, list[list[str]]] = {}
        self.lock: Lock = Lock()

    def __enter__(self):
        """See super docs.

        The InMemoryBackend uses a simple Lock to synchronize all
        access.
        """
        super().__enter__()
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        self.lock.release()

    def _ensure_tenant_id(self, tenant_id):
        if not tenant_id in self.resources:
            self.resources[tenant_id] = []

    def register_resource_type(self, resource_type: ResourceType):
        super().register_resource_type(resource_type)
        self.unique_attributes[resource_type.id] = self.collect_resource_unique_attrs(
            resource_type, self.schemas
        )

    def query_resources(
        self,
        tenant_id: str,
        search_request: SearchRequest,
        resource_type_id: str | None = None,
    ) -> tuple[int, list[Resource]]:
        self._ensure_tenant_id(tenant_id)

        start_index = (search_request.start_index or 1) - 1

        tree = None
        if search_request.filter is not None:
            token_stream = lexer.SCIMLexer().tokenize(search_request.filter)
            tree = SCIMParser().parse(token_stream)

        found_resources = [
            r
            for r in self.resources[tenant_id]
            if (resource_type_id is None or r.meta.resource_type == resource_type_id)
            and (tree is None or evaluate_filter(r, tree))
        ]

        if search_request.sort_by is not None:
            descending = search_request.sort_order == SearchRequest.SortOrder.descending
            sort_operator = ResolveSortOperator(search_request.sort_by)

            # To ensure that unset attributes are sorted last (when ascending, as defined in the RFC),
            # we have to divide the result set into a set and unset subset.
            unset_values = []
            set_values = []
            for resource in found_resources:
                result = sort_operator(resource)
                if result is None:
                    unset_values.append(resource)
                else:
                    set_values.append((resource, result))

            set_values.sort(key=operator.itemgetter(1), reverse=descending)
            set_values = [value[0] for value in set_values]
            if descending:
                found_resources = unset_values + set_values
            else:
                found_resources = set_values + unset_values

        found_resources = found_resources[start_index:]
        if search_request.count is not None:
            found_resources = found_resources[: search_request.count]
        return len(found_resources), found_resources

    def _get_resource_idx(self, tenant_id: str, resource_type_id: str, object_id: str) -> int | None:
        self._ensure_tenant_id(tenant_id)
        return next(
            (
                idx
                for idx, r in enumerate(self.resources[tenant_id])
                if r.meta.resource_type == resource_type_id and r.id == object_id
            ),
            None,
        )

    def get_resource(self, tenant_id: str, resource_type_id: str, object_id: str) -> Resource | None:
        self._ensure_tenant_id(tenant_id)
        resource_dict_idx = self._get_resource_idx(tenant_id, resource_type_id, object_id)
        if resource_dict_idx is not None:
            return self.resources[tenant_id][resource_dict_idx].model_copy(deep=True)
        return None

    def delete_resource(self, tenant_id: str, resource_type_id: str, object_id: str) -> bool:
        self._ensure_tenant_id(tenant_id)
        found = self.get_resource(tenant_id, resource_type_id, object_id)
        if found:
            self.resources[tenant_id] = [
                r
                for r in self.resources[tenant_id]
                if not (r.meta.resource_type == resource_type_id and r.id == object_id)
            ]
            return True
        return False

    def create_resource(
        self, tenant_id: str, resource_type_id: str, resource: Resource
    ) -> Resource | None:
        self._ensure_tenant_id(tenant_id)
        resource = resource.model_copy(deep=True)
        resource.id = uuid.uuid4().hex
        utcnow = datetime.datetime.now(datetime.timezone.utc)
        resource.meta = Meta(
            resource_type=self.resource_types[resource_type_id].name,
            created=utcnow,
            last_modified=utcnow,
            location="/v2"
            + self.resource_types[resource_type_id].endpoint
            + "/"
            + resource.id,
        )
        self._touch_resource(resource, utcnow)

        for unique_attribute in self.unique_attributes[resource_type_id]:
            new_value = unique_attribute.get_attribute(resource)
            for existing_resource in self.resources[tenant_id]:
                if existing_resource.meta.resource_type == resource_type_id:
                    existing_value = unique_attribute.get_attribute(existing_resource)
                    if existing_value == new_value:
                        raise SCIMException(Error.make_uniqueness_error())

        self.resources[tenant_id].append(resource)
        return resource

    @staticmethod
    def _touch_resource(resource: Resource, last_modified: datetime.datetime):
        """Touches a resource (updates last_modified and version).

        Version is generated by hashing last_modified. Another option
        would be to hash the entire resource instead.
        """
        resource.meta.last_modified = last_modified
        etag = generate_etag(pickle.dumps(resource.meta.last_modified))
        resource.meta.version = f'W/"{etag}"'

    def update_resource(
        self, tenant_id: str, resource_type_id: str, resource: Resource
    ) -> Resource | None:
        self._ensure_tenant_id(tenant_id)
        
        found_res_idx = self._get_resource_idx(tenant_id, resource_type_id, resource.id)
        if found_res_idx is not None:
            updated_resource = self.models_dict[resource_type_id].model_validate(
                resource.model_dump()
            )
            self._touch_resource(
                updated_resource, datetime.datetime.now(datetime.timezone.utc)
            )

            for unique_attribute in self.unique_attributes[resource_type_id]:
                new_value = unique_attribute.get_attribute(updated_resource)
                for existing_resource in self.resources[tenant_id]:
                    if (
                        existing_resource.meta.resource_type == resource_type_id
                        and existing_resource.id != updated_resource.id
                    ):
                        existing_value = unique_attribute.get_attribute(
                            existing_resource
                        )
                        if existing_value == new_value:
                            raise SCIMException(Error.make_uniqueness_error())

            self.resources[tenant_id][found_res_idx] = updated_resource
            return updated_resource
        return None

from werkzeug import Request

class TenantProvider:

    def get_tenant_id(self, request: Request):
        # this does in general return "" for single tenant mode
        # for testing purposes in this default provider we return the
        # value if it's of type Bearer and the value starts with a !

        # in the real world you want to have a provider that extracts the
        # tenantid from a jwtoken or from another header like x-tenant-id
        if request and "Authorization" in request.headers:
            values = request.headers["Authorization"].split(" ")
            if len(values) > 1 and values[0].lower() == "bearer":
                tenant_id = values[1]
                # Remove the leading "!" if present
                if tenant_id.startswith("!"):
                    return tenant_id[1:]  # Remove the "!" and return the rest

        return ""

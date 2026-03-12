class MudrexResponse(dict):
    """API response that supports both dict-style and attribute-style access.

    Examples::

        resp = client.place_order(...)
        resp["order_id"]   # dict access
        resp.order_id      # attribute access
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'MudrexResponse' has no field '{name}'")

    def __repr__(self):
        return f"MudrexResponse({dict.__repr__(self)})"

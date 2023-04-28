def get_fields_queried(query_context, app_label_prefix="testapp_"):
    sql = query_context[0]["sql"]
    fields = (
        sql[sql.index('"') : sql.index("FROM")]
        .replace('"', "")
        .replace(" ", "")
        .replace(app_label_prefix, "")
        .split(",")
    )
    return set(fields)  # format: [ 'django_session.session_key', ... ]

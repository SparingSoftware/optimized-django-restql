def flatten(items: [list, tuple, set]) -> list:
    result = []

    for item in items:
        if isinstance(item, (list, tuple, set)):
            result += flatten(item)
        else:
            result.append(item)

    return result

def csrf(client):
    client.get("/")
    with client.session_transaction() as session:
        return session["csrf_token"]


def test_invalid_microsoft_link_is_visible_error(client):
    response = client.post(
        "/api/graph/link",
        json={"link": "https://example.com/prices.xlsx"},
        headers={"X-CSRF-Token": csrf(client)},
    )
    assert response.status_code == 422
    assert "OneDrive or SharePoint" in response.json["error"]


def test_non_xlsx_graph_selection_is_rejected(client):
    response = client.post(
        "/api/graph/select",
        json={"itemId": "item-1", "driveId": "drive-1", "name": "prices.csv"},
        headers={"X-CSRF-Token": csrf(client)},
    )
    assert response.status_code == 422
    assert ".xlsx" in response.json["error"]

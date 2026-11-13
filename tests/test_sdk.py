"""Public SDK page adapters and forward-compatible record serialization."""

import json
import unittest
from unittest.mock import patch

from atproto import models
from atproto_client.models.dot_dict import DotDict
from atproto_client.utils import PaginatedResponse
from test_service import CID, DID

from skyloom.domain import author_from
from skyloom.sdk import model_data, page_items


class SdkAdapters(unittest.TestCase):
    def test_unknown_dotdict_uses_public_serializer_without_attribute_probing(self):
        raw = {
            "$type": "example.invalid.future",
            "futureField": {"keepNull": None, "keepList": [1, {"nestedValue": "invented"}]},
        }
        value = DotDict(raw)
        self.assertTrue(hasattr(value, "model_dump"))
        self.assertIsNone(value.model_dump)
        result = model_data(value)
        self.assertIsInstance(result, dict)
        self.assertEqual(result, raw)
        self.assertEqual(json.loads(json.dumps(result)), raw)

    def test_plain_fixture_dictionaries_remain_unchanged(self):
        value = {"record": {"unknownField": None}}
        self.assertIs(model_data(value), value)
        self.assertIsNone(model_data(None))

    def test_sdk_profile_roundtrip_preserves_nested_unknown_labels_and_fields(self):
        record = {
            "$type": "app.bsky.actor.profile",
            "displayName": "Invented",
            "description": "Before",
            "labels": {
                "$type": "example.invalid.futureLabels",
                "values": [{"privateExtension": None}],
            },
            "futureProfile": {"nestedField": ["keep", None]},
        }
        response = models.ComAtprotoRepoGetRecord.Response(
            uri=f"at://{DID}/app.bsky.actor.profile/self", cid=CID, value=record
        )
        snapshot = model_data(response)["value"]
        snapshot["description"] = "After"
        write = models.ComAtprotoRepoPutRecord.Data(
            repo=DID,
            collection="app.bsky.actor.profile",
            rkey="self",
            swap_record=CID,
            record=snapshot,
        )
        saved = model_data(write)["record"]
        self.assertEqual(saved["description"], "After")
        self.assertEqual(saved["labels"], record["labels"])
        self.assertEqual(saved["futureProfile"], record["futureProfile"])

    def test_sdk_gate_roundtrip_preserves_unknown_rule_and_record_fields(self):
        rule = {"$type": "example.invalid.futureReplyRule", "futureRule": {"unknownValue": None}}
        record = {
            "$type": "app.bsky.feed.threadgate",
            "post": f"at://{DID}/app.bsky.feed.post/invented",
            "createdAt": "2026-11-13T00:00:00Z",
            "allow": [rule],
            "futureGate": {"unknownList": [1, 2]},
        }
        response = models.ComAtprotoRepoGetRecord.Response(
            uri=f"at://{DID}/app.bsky.feed.threadgate/invented", cid=CID, value=record
        )
        snapshot = model_data(response)["value"]
        write = models.ComAtprotoRepoPutRecord.Data(
            repo=DID,
            collection="app.bsky.feed.threadgate",
            rkey="invented",
            swap_record=CID,
            record=snapshot,
        )
        saved = model_data(write)["record"]
        self.assertEqual(saved["allow"], [rule])
        self.assertEqual(saved["futureGate"], record["futureGate"])

    def test_typed_page_access_preserves_cursor_and_ignores_unneeded_subject(self):
        response = models.AppBskyGraphGetFollowers.Response(
            subject={
                "did": DID,
                "handle": "invented.invalid",
                "displayName": "Subject must not be serialized",
            },
            followers=[
                {
                    "did": "did:plc:inventedother",
                    "handle": "other.invalid",
                    "displayName": "Other",
                    "viewer": {"muted": True},
                }
            ],
            cursor="next-invented-page",
        )
        self.assertIsInstance(response, PaginatedResponse)
        with patch.object(
            type(response),
            "model_dump",
            side_effect=AssertionError("Do not dump unused page metadata"),
        ):
            people = page_items(response, author_from)
        self.assertEqual(len(people), 1)
        self.assertTrue(people[0].muted)
        self.assertEqual(people[0].handle, "other.invalid")
        self.assertEqual(response.cursor, "next-invented-page")
        self.assertIsInstance(page_items(response)[0], dict)
        self.assertEqual(len(response.followers), 1)

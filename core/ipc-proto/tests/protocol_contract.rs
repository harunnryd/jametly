use ipc_proto::{ErrorBody, ErrorCode, Event, Reply, Request, WireMessage};
use serde_json::{json, Value};

#[test]
fn request_full_round_trip() {
    let req = Request {
        id: "req-abc".into(),
        method: "chat.stream".into(),
        params: json!({"user_text": "hi", "thread_id": "t-1"}),
    };
    let s = serde_json::to_string(&req).unwrap();
    let back: Request = serde_json::from_str(&s).unwrap();
    assert_eq!(req, back);
}

#[test]
fn request_missing_params_defaults_to_null() {
    // `params` is optional on the wire; default is `Value::Null`.
    let raw = r#"{"id":"r","method":"echo"}"#;
    let req: Request = serde_json::from_str(raw).unwrap();
    assert_eq!(req.id, "r");
    assert_eq!(req.method, "echo");
    assert_eq!(req.params, Value::Null);
}

#[test]
fn reply_ok_unwraps_correctly() {
    let raw = r#"{"id":"req-1","result":{"answer":"42"}}"#;
    let reply: Reply = serde_json::from_str(raw).unwrap();
    match reply {
        Reply::Ok(r) => {
            assert_eq!(r.id, "req-1");
            assert_eq!(r.result, json!({"answer": "42"}));
        }
        Reply::Err(_) => panic!("expected Ok, got Err"),
    }
}

#[test]
fn reply_err_unwraps_correctly() {
    let raw =
        r#"{"id":"req-2","error":{"code":"INVALID_REQUEST","message":"bad","retryable":false}}"#;
    let reply: Reply = serde_json::from_str(raw).unwrap();
    match reply {
        Reply::Err(r) => {
            assert_eq!(r.id, "req-2");
            assert_eq!(r.error["code"], "INVALID_REQUEST");
        }
        Reply::Ok(_) => panic!("expected Err, got Ok"),
    }
}

#[test]
fn request_rejects_missing_id() {
    let raw = r#"{"method":"echo"}"#;
    let res: Result<Request, _> = serde_json::from_str(raw);
    assert!(res.is_err());
}

#[test]
fn request_rejects_missing_method() {
    let raw = r#"{"id":"r"}"#;
    let res: Result<Request, _> = serde_json::from_str(raw);
    assert!(res.is_err());
}

#[test]
fn error_body_round_trip_all_codes() {
    let codes = [
        ErrorCode::ParseError,
        ErrorCode::InvalidRequest,
        ErrorCode::IpcSchemaVersion,
        ErrorCode::ProviderRateLimit,
        ErrorCode::ProviderAuth,
        ErrorCode::ProviderUnavailable,
        ErrorCode::PythonTimeout,
        ErrorCode::AudioDeviceLost,
        ErrorCode::OcrFailed,
        ErrorCode::MeetingNotFound,
        ErrorCode::Internal,
    ];
    for code in codes {
        let body = ErrorBody {
            code,
            message: format!("{code:?} test"),
            retryable: false,
        };
        let s = serde_json::to_string(&body).unwrap();
        let back: ErrorBody = serde_json::from_str(&s).unwrap();
        assert_eq!(body, back);
    }
}

#[test]
fn error_body_serializes_codes_in_screaming_snake() {
    let body = ErrorBody {
        code: ErrorCode::ProviderRateLimit,
        message: "x".into(),
        retryable: true,
    };
    let v: Value = serde_json::to_value(&body).unwrap();
    assert_eq!(v["code"], "PROVIDER_RATE_LIMIT");
}

#[test]
fn event_full_round_trip() {
    let ev = Event {
        method: "stream.event".into(),
        params: json!({"correlation_id": "req-1", "kind": "token", "data": "hi"}),
    };
    let s = serde_json::to_string(&ev).unwrap();
    let back: Event = serde_json::from_str(&s).unwrap();
    assert_eq!(ev, back);
}

#[test]
fn event_never_serializes_an_id() {
    let ev = Event {
        method: "audio.level".into(),
        params: json!({"ts_ms": 10, "rms_db": -12.5}),
    };
    let v: Value = serde_json::to_value(&ev).unwrap();
    assert!(
        v.get("id").is_none(),
        "events are fire-and-forget and must not carry an id: {v}"
    );
}

#[test]
fn event_missing_params_defaults_to_null() {
    let ev: Event = serde_json::from_str(r#"{"method":"python.crash"}"#).unwrap();
    assert_eq!(ev.method, "python.crash");
    assert_eq!(ev.params, Value::Null);
}

#[test]
fn event_accepts_explicit_null_id() {
    let ev: Event =
        serde_json::from_str(r#"{"id":null,"method":"transcript.partial","params":{}}"#).unwrap();
    assert_eq!(ev.method, "transcript.partial");
}

#[test]
fn event_rejects_non_null_id() {
    let raw = r#"{"id":"req-1","method":"stream.event","params":{}}"#;
    let res: Result<Event, _> = serde_json::from_str(raw);
    assert!(res.is_err(), "a correlated id must not parse as an Event");
}

#[test]
fn event_rejects_missing_method() {
    let res: Result<Event, _> = serde_json::from_str(r#"{"params":{}}"#);
    assert!(res.is_err());
}

#[test]
fn event_rejects_empty_method() {
    let res: Result<Event, _> = serde_json::from_str(r#"{"method":"","params":{}}"#);
    assert!(res.is_err());
}

#[test]
fn event_rejects_unknown_field() {
    let raw = r#"{"method":"stream.event","params":{},"result":{}}"#;
    let res: Result<Event, _> = serde_json::from_str(raw);
    assert!(res.is_err());
}

#[test]
fn event_line_is_not_parsed_as_reply() {
    let raw = r#"{"method":"stream.event","params":{"correlation_id":"req-1","kind":"token"}}"#;
    let res: Result<Reply, _> = serde_json::from_str(raw);
    assert!(res.is_err(), "event line must not deserialize as a Reply");
}

#[test]
fn wire_message_discriminates_request() {
    let raw = r#"{"id":"r1","method":"echo","params":{"x":1}}"#;
    match serde_json::from_str::<WireMessage>(raw).unwrap() {
        WireMessage::Request(r) => assert_eq!(r.id, "r1"),
        other => panic!("expected Request, got {other:?}"),
    }
}

#[test]
fn wire_message_discriminates_reply_ok() {
    let raw = r#"{"id":"r1","result":{"x":1}}"#;
    match serde_json::from_str::<WireMessage>(raw).unwrap() {
        WireMessage::Reply(Reply::Ok(r)) => assert_eq!(r.id, "r1"),
        other => panic!("expected Reply::Ok, got {other:?}"),
    }
}

#[test]
fn wire_message_discriminates_reply_err() {
    let raw = r#"{"id":"r1","error":{"code":"INTERNAL","message":"boom"}}"#;
    match serde_json::from_str::<WireMessage>(raw).unwrap() {
        WireMessage::Reply(Reply::Err(r)) => assert_eq!(r.error["code"], "INTERNAL"),
        other => panic!("expected Reply::Err, got {other:?}"),
    }
}

#[test]
fn wire_message_discriminates_event() {
    let raw = r#"{"method":"stream.event","params":{"kind":"done"}}"#;
    match serde_json::from_str::<WireMessage>(raw).unwrap() {
        WireMessage::Event(e) => assert_eq!(e.method, "stream.event"),
        other => panic!("expected Event, got {other:?}"),
    }
}

#[test]
fn wire_message_discriminates_event_with_null_id() {
    let raw = r#"{"id":null,"method":"audio.level","params":{"rms_db":-3.0}}"#;
    match serde_json::from_str::<WireMessage>(raw).unwrap() {
        WireMessage::Event(e) => assert_eq!(e.method, "audio.level"),
        other => panic!("expected Event, got {other:?}"),
    }
}

#[test]
fn wire_message_rejects_garbage() {
    assert!(serde_json::from_str::<WireMessage>(r#"{"nonsense":true}"#).is_err());
    assert!(serde_json::from_str::<WireMessage>("not json").is_err());
}

#[test]
fn envelope_shapes_snapshot() {
    let envelopes = json!([
        Request {
            id: "req-1".into(),
            method: "chat.stream".into(),
            params: json!({"thread_id": "t-1", "user_text": "hi"}),
        },
        Reply::Ok(ipc_proto::ReplyOk {
            id: "req-1".into(),
            result: json!({"stream_id": "s-1"}),
        }),
        Reply::Err(ipc_proto::ReplyErr {
            id: "req-2".into(),
            error: serde_json::to_value(ErrorBody {
                code: ErrorCode::ProviderRateLimit,
                message: "anthropic 429".into(),
                retryable: true,
            })
            .unwrap(),
        }),
        Event {
            method: "stream.event".into(),
            params: json!({"correlation_id": "req-1", "kind": "token", "data": "he"}),
        },
    ]);
    insta::assert_yaml_snapshot!(envelopes);
}

proptest::proptest! {
    #[test]
    fn wire_message_parse_yields_a_typed_result_and_never_panics(line in ".*") {
        let _ = serde_json::from_str::<WireMessage>(&line);
    }

    #[test]
    fn event_round_trips_for_any_method_and_params(
        method in "[a-z][a-z0-9._-]{0,30}",
        data in ".*",
    ) {
        let ev = Event {
            method,
            params: json!({"correlation_id": "req-1", "kind": "token", "data": data}),
        };
        let s = serde_json::to_string(&ev).unwrap();
        let back: Event = serde_json::from_str(&s).unwrap();
        proptest::prop_assert_eq!(ev, back);
    }

    #[test]
    fn request_lines_never_discriminate_as_events(
        id in "[a-zA-Z0-9-]{1,20}",
        method in "[a-z][a-z0-9._-]{0,30}",
    ) {
        let raw = serde_json::to_string(&Request {
            id: id.clone(),
            method,
            params: json!({}),
        }).unwrap();
        match serde_json::from_str::<WireMessage>(&raw).unwrap() {
            WireMessage::Request(r) => proptest::prop_assert_eq!(r.id, id),
            other => proptest::prop_assert!(false, "expected Request, got {:?}", other),
        }
    }
}

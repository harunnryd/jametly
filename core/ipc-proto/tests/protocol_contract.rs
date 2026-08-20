//! Cross-crate protocol contract tests for `ipc-proto`.
//!
//! Asserts the wire format between Rust host and Python sidecar. The Python
//! side mirrors these types via Pydantic; if this test passes after any
//! change to `lib.rs`, the Python side must be updated in lockstep.

use ipc_proto::{ErrorBody, ErrorCode, Reply, ReplyErr, ReplyOk, Request};
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

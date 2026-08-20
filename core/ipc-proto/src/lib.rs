use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

/// Request envelope: Rust → Python.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Request {
    pub id: String,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

/// Successful reply: Python → Rust.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReplyOk {
    pub id: String,
    pub result: Value,
}

/// Error reply: Python → Rust.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReplyErr {
    pub id: String,
    pub error: Value,
}

/// Reply envelope: Python → Rust. Either ok or err — flattened on the wire.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Reply {
    Ok(ReplyOk),
    Err(ReplyErr),
}

/// Canonical error codes (per `docs/architecture/01-ipc.md`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ErrorCode {
    ParseError,
    InvalidRequest,
    IpcSchemaVersion,
    ProviderRateLimit,
    ProviderAuth,
    ProviderUnavailable,
    PythonTimeout,
    AudioDeviceLost,
    OcrFailed,
    MeetingNotFound,
    Internal,
}

/// Typed error used by the Python sidecar when serializing failures.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ErrorBody {
    pub code: ErrorCode,
    pub message: String,
    #[serde(default)]
    pub retryable: bool,
}

/// Top-level parse / shape error for malformed lines on the wire.
#[derive(Debug, Error)]
pub enum WireError {
    #[error("malformed JSON line: {0}")]
    Json(#[from] serde_json::Error),
    #[error("missing field `{0}`")]
    MissingField(&'static str),
}

#[cfg(test)]
mod inline_tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn request_round_trip() {
        let r = Request {
            id: "req-1".into(),
            method: "echo".into(),
            params: json!({"x": "hi"}),
        };
        let s = serde_json::to_string(&r).unwrap();
        let back: Request = serde_json::from_str(&s).unwrap();
        assert_eq!(r, back);
    }

    #[test]
    fn reply_ok_round_trip() {
        let r = ReplyOk {
            id: "req-1".into(),
            result: json!({"x": "hi"}),
        };
        let s = serde_json::to_string(&r).unwrap();
        let back: ReplyOk = serde_json::from_str(&s).unwrap();
        assert_eq!(r, back);
    }

    #[test]
    fn reply_err_round_trip() {
        let r = ReplyErr {
            id: "req-1".into(),
            error: json!({
                "code": "PARSE_ERROR",
                "message": "missing brace"
            }),
        };
        let s = serde_json::to_string(&r).unwrap();
        let back: ReplyErr = serde_json::from_str(&s).unwrap();
        assert_eq!(r, back);
    }

    #[test]
    fn error_body_canonical_codes() {
        let e = ErrorBody {
            code: ErrorCode::ProviderRateLimit,
            message: "anthropic 429".into(),
            retryable: true,
        };
        let s = serde_json::to_string(&e).unwrap();
        assert!(s.contains("PROVIDER_RATE_LIMIT"));
        assert!(s.contains("\"retryable\":true"));
    }

    #[test]
    fn error_body_rejects_unknown_code() {
        let bogus = json!({"code": "TOTALLY_MADE_UP", "message": "x", "retryable": false});
        let res: Result<ErrorBody, _> = serde_json::from_value(bogus);
        assert!(res.is_err());
    }
}

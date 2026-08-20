use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Request {
    pub id: String,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReplyOk {
    pub id: String,
    pub result: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReplyErr {
    pub id: String,
    pub error: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Reply {
    Ok(ReplyOk),
    Err(ReplyErr),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "EventRepr")]
pub struct Event {
    pub method: String,
    pub params: Value,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct EventRepr {
    #[serde(default)]
    id: Option<Value>,
    method: String,
    #[serde(default)]
    params: Value,
}

impl TryFrom<EventRepr> for Event {
    type Error = String;

    fn try_from(repr: EventRepr) -> Result<Self, Self::Error> {
        match repr.id {
            None | Some(Value::Null) => {}
            Some(id) => return Err(format!("event `id` must be absent or null, got {id}")),
        }
        if repr.method.is_empty() {
            return Err("event `method` must not be empty".into());
        }
        Ok(Event {
            method: repr.method,
            params: repr.params,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum WireMessage {
    Request(Request),
    Reply(Reply),
    Event(Event),
}

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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ErrorBody {
    pub code: ErrorCode,
    pub message: String,
    #[serde(default)]
    pub retryable: bool,
}

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

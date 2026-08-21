use std::collections::HashMap;
use std::fmt;
use std::sync::{Arc, RwLock};

use thiserror::Error;

#[derive(Clone, PartialEq, Eq)]
pub struct SecretKey(String);

impl SecretKey {
    pub fn parse(value: &str) -> Result<Self, SecureStoreError> {
        let valid = (value == "openai_api_key")
            || (value == "anthropic_api_key")
            || (value.strip_prefix("provider_").is_some_and(|suffix| {
                !suffix.is_empty()
                    && suffix.chars().all(|character| {
                        character.is_ascii_alphanumeric() || "._-".contains(character)
                    })
            }));
        if valid {
            Ok(Self(value.to_owned()))
        } else {
            Err(SecureStoreError::InvalidKey)
        }
    }
}

impl fmt::Debug for SecretKey {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("SecretKey(REDACTED)")
    }
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum SecureStoreError {
    #[error("secret-store access denied")]
    Denied,
    #[error("secret-store unavailable")]
    Unavailable,
    #[error("secret key is not in the approved provider namespace")]
    InvalidKey,
    #[error("secret-store backend failure")]
    Backend,
}

pub trait SecretStore {
    fn get(&self, key: &SecretKey) -> Result<Option<String>, SecureStoreError>;
    fn set(&self, key: &SecretKey, value: &str) -> Result<(), SecureStoreError>;
    fn delete(&self, key: &SecretKey) -> Result<(), SecureStoreError>;
}

#[derive(Clone)]
pub struct FakeSecretStore {
    values: Arc<RwLock<HashMap<String, String>>>,
    failure: Option<StoreFailure>,
}

#[derive(Clone, Copy)]
enum StoreFailure {
    Denied,
    Unavailable,
}

impl FakeSecretStore {
    pub fn new() -> Self {
        Self {
            values: Arc::new(RwLock::new(HashMap::new())),
            failure: None,
        }
    }

    pub fn denied() -> Self {
        Self {
            values: Arc::new(RwLock::new(HashMap::new())),
            failure: Some(StoreFailure::Denied),
        }
    }

    pub fn unavailable() -> Self {
        Self {
            values: Arc::new(RwLock::new(HashMap::new())),
            failure: Some(StoreFailure::Unavailable),
        }
    }

    fn failure(&self) -> Option<SecureStoreError> {
        self.failure.map(|failure| match failure {
            StoreFailure::Denied => SecureStoreError::Denied,
            StoreFailure::Unavailable => SecureStoreError::Unavailable,
        })
    }
}

impl Default for FakeSecretStore {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Debug for FakeSecretStore {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("FakeSecretStore")
            .field(
                "entry_count",
                &self.values.read().map(|values| values.len()).unwrap_or(0),
            )
            .finish()
    }
}

impl SecretStore for FakeSecretStore {
    fn get(&self, key: &SecretKey) -> Result<Option<String>, SecureStoreError> {
        if let Some(error) = self.failure() {
            return Err(error);
        }
        self.values
            .read()
            .map_err(|_| SecureStoreError::Backend)
            .map(|values| values.get(&key.0).cloned())
    }

    fn set(&self, key: &SecretKey, value: &str) -> Result<(), SecureStoreError> {
        if let Some(error) = self.failure() {
            return Err(error);
        }
        self.values
            .write()
            .map_err(|_| SecureStoreError::Backend)?
            .insert(key.0.clone(), value.to_owned());
        Ok(())
    }

    fn delete(&self, key: &SecretKey) -> Result<(), SecureStoreError> {
        if let Some(error) = self.failure() {
            return Err(error);
        }
        self.values
            .write()
            .map_err(|_| SecureStoreError::Backend)?
            .remove(&key.0);
        Ok(())
    }
}

use secure_store::{FakeSecretStore, SecretKey, SecretStore, SecureStoreError};

#[test]
fn keys_accept_only_the_provider_namespace() {
    assert!(SecretKey::parse("openai_api_key").is_ok());
    assert!(SecretKey::parse("anthropic_api_key").is_ok());
    assert!(SecretKey::parse("provider_local_1").is_ok());
    assert!(SecretKey::parse("license_key").is_err());
    assert!(SecretKey::parse("../escape").is_err());
    assert!(SecretKey::parse("provider_").is_err());
}

#[test]
fn fake_store_round_trips_replaces_and_deletes_secrets() {
    let store = FakeSecretStore::new();
    let key = SecretKey::parse("openai_api_key").unwrap();

    assert_eq!(store.get(&key).unwrap(), None);
    store.set(&key, "first").unwrap();
    assert_eq!(store.get(&key).unwrap().as_deref(), Some("first"));
    store.set(&key, "second").unwrap();
    assert_eq!(store.get(&key).unwrap().as_deref(), Some("second"));
    store.delete(&key).unwrap();
    assert_eq!(store.get(&key).unwrap(), None);
}

#[test]
fn secrets_and_keys_never_appear_in_debug_or_error_output() {
    let store = FakeSecretStore::new();
    let key = SecretKey::parse("anthropic_api_key").unwrap();
    store.set(&key, "super-secret-value").unwrap();

    assert!(!format!("{store:?}").contains("super-secret-value"));
    assert!(!format!("{key:?}").contains("anthropic_api_key"));
    assert!(!SecureStoreError::Denied
        .to_string()
        .contains("anthropic_api_key"));
}

#[test]
fn fake_store_surfaces_denied_and_unavailable_without_plaintext_fallback() {
    let key = SecretKey::parse("openai_api_key").unwrap();
    let denied = FakeSecretStore::denied();
    assert!(matches!(denied.get(&key), Err(SecureStoreError::Denied)));
    assert!(matches!(
        denied.set(&key, "secret"),
        Err(SecureStoreError::Denied)
    ));

    let unavailable = FakeSecretStore::unavailable();
    assert!(matches!(
        unavailable.get(&key),
        Err(SecureStoreError::Unavailable)
    ));
}

#[test]
fn trait_supports_runtime_selected_platform_stores() {
    fn accepts_store(_: &dyn SecretStore) {}
    accepts_store(&FakeSecretStore::new());
}

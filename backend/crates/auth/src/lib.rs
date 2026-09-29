use anyhow::Result;
use argon2::{
    Argon2,
    password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString, rand_core::OsRng},
};
use chrono::Utc;
use datavault_domain::User;
use datavault_storage::Db;
use jsonwebtoken::{Algorithm, DecodingKey, EncodingKey, Header, Validation, decode, encode};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use uuid::Uuid;

// ─── Token Claims ─────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String, // user UUID
    pub email: String,
    pub exp: usize,
    pub iat: usize,
    #[serde(default)]
    pub jti: String,
}

// ─── Auth Service ─────────────────────────────────────────────────────────────

#[derive(Clone)]
pub struct AuthService {
    db: Db,
    jwt_secret: String,
    jwt_expiry_secs: i64,
}

impl AuthService {
    pub fn new(db: Db, jwt_secret: String) -> Self {
        Self {
            db,
            jwt_secret,
            jwt_expiry_secs: 7 * 24 * 3600, // 7 days
        }
    }

    /// Hash a plaintext password with Argon2id
    pub fn hash_password(&self, password: &str) -> Result<String> {
        let salt = SaltString::generate(&mut OsRng);
        let argon2 = Argon2::default();
        let hash = argon2
            .hash_password(password.as_bytes(), &salt)
            .map_err(|e| anyhow::anyhow!("hash error: {e}"))?
            .to_string();
        Ok(hash)
    }

    /// Verify a plaintext password against a stored Argon2id hash
    pub fn verify_password(&self, password: &str, hash: &str) -> bool {
        let Ok(parsed) = PasswordHash::new(hash) else {
            return false;
        };
        Argon2::default()
            .verify_password(password.as_bytes(), &parsed)
            .is_ok()
    }

    /// Create a JWT bearing the user's ID and email
    pub fn create_jwt(&self, user: &User) -> Result<String> {
        let now = Utc::now().timestamp() as usize;
        let claims = Claims {
            sub: user.id.to_string(),
            email: user.email.clone(),
            iat: now,
            exp: now + self.jwt_expiry_secs as usize,
            jti: Uuid::new_v4().to_string(),
        };
        let token = encode(
            &Header::default(),
            &claims,
            &EncodingKey::from_secret(self.jwt_secret.as_bytes()),
        )?;
        Ok(token)
    }

    /// Decode and validate a JWT; returns the claims on success
    pub fn verify_jwt(&self, token: &str) -> Result<Claims> {
        let mut validation = Validation::new(Algorithm::HS256);
        validation.leeway = 0;
        let data = decode::<Claims>(
            token,
            &DecodingKey::from_secret(self.jwt_secret.as_bytes()),
            &validation,
        )?;
        Ok(data.claims)
    }

    /// Register a new local user and return (user, jwt)
    pub async fn register(
        &self,
        email: &str,
        name: Option<&str>,
        password: &str,
    ) -> Result<(User, String)> {
        if password.chars().count() < 8 || password.len() > 1024 {
            anyhow::bail!("password must contain 8 or more characters (maximum 1024 bytes)");
        }
        if email.len() > 254 || !email.contains('@') || email.chars().any(char::is_whitespace) {
            anyhow::bail!("enter a valid email address");
        }
        // Reject if email already exists
        if self.db.get_user_by_email(email).await?.is_some() {
            anyhow::bail!("email already registered");
        }
        let hash = self.hash_password(password)?;
        let user = self.db.create_user(email, name, Some(&hash)).await?;
        let token = self.create_jwt(&user)?;

        // Store session
        self.persist_session(user.id, &token).await?;

        Ok((user, token))
    }

    /// Validate credentials and return (user, jwt)
    pub async fn login(&self, email: &str, password: &str) -> Result<(User, String)> {
        let user = self
            .db
            .get_user_by_email(email)
            .await?
            .ok_or_else(|| anyhow::anyhow!("invalid credentials"))?;

        if !user.is_active {
            anyhow::bail!("account disabled");
        }

        let hash = user
            .password_hash
            .as_deref()
            .ok_or_else(|| anyhow::anyhow!("oauth account — use provider login"))?;

        if !self.verify_password(password, hash) {
            anyhow::bail!("invalid credentials");
        }

        let token = self.create_jwt(&user)?;
        self.persist_session(user.id, &token).await?;

        Ok((user, token))
    }

    /// Verify an incoming bearer token and return the user
    pub async fn authenticate(&self, token: &str) -> Result<User> {
        let claims = self.verify_jwt(token)?;
        let uid = Uuid::parse_str(&claims.sub)?;
        let hash = format!("{:x}", Sha256::digest(token.as_bytes()));
        let active: bool = sqlx::query_scalar(
            "SELECT EXISTS(SELECT 1 FROM sessions WHERE token_hash = $1 AND user_id = $2 AND expires_at > NOW())"
        ).bind(hash).bind(uid).fetch_one(&self.db.pool).await?;
        if !active {
            anyhow::bail!("session expired or revoked");
        }
        let user = self
            .db
            .get_user_by_id(uid)
            .await?
            .ok_or_else(|| anyhow::anyhow!("user not found"))?;
        if !user.is_active {
            anyhow::bail!("account disabled");
        }
        Ok(user)
    }

    /// Revoke only the current session; other signed-in devices remain active.
    pub async fn logout(&self, token: &str) -> Result<()> {
        let hash = format!("{:x}", Sha256::digest(token.as_bytes()));
        sqlx::query("DELETE FROM sessions WHERE token_hash = $1")
            .bind(hash)
            .execute(&self.db.pool)
            .await?;
        Ok(())
    }

    // Persist session hash to postgres for revocation support
    async fn persist_session(&self, user_id: Uuid, token: &str) -> Result<()> {
        let hash = format!("{:x}", Sha256::digest(token.as_bytes()));
        let expires_at = Utc::now() + chrono::Duration::seconds(self.jwt_expiry_secs);

        sqlx::query!(
            "INSERT INTO sessions (user_id, token_hash, expires_at)
             VALUES ($1, $2, $3)
             ON CONFLICT (token_hash) DO NOTHING",
            user_id,
            hash,
            expires_at,
        )
        .execute(&self.db.pool)
        .await?;

        Ok(())
    }
}

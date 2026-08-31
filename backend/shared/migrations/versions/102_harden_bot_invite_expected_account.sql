-- 102: Never weaken a fixed-account reset into an unrestricted invitation.
--
-- If a custom Bot account is removed while one of its reauthorization links
-- is pending, delete that invitation as well.  SET NULL would otherwise turn
-- the callback's expected-account check off and allow a different identity.

ALTER TABLE bot_oauth_invites
    DROP CONSTRAINT IF EXISTS bot_oauth_invites_expected_bot_user_id_fkey;

ALTER TABLE bot_oauth_invites
    ADD CONSTRAINT bot_oauth_invites_expected_bot_user_id_fkey
    FOREIGN KEY (expected_bot_user_id)
    REFERENCES bot_accounts(platform_user_id)
    ON DELETE CASCADE;

"""Reusable original-world fixtures for Role-play tests."""

from shared.roleplay import (
    CanonMode,
    ChannelStage,
    CharacterKnowledge,
    CharacterSheet,
    LoreEntry,
    Relationship,
    RelationshipState,
    RoleplayPackage,
    Scene,
    SourceKind,
    SpoilerPolicy,
    WorldSnapshot,
)


def sample_roleplay_package() -> RoleplayPackage:
    return RoleplayPackage(
        schema_version=1,
        name="月港守望者拉娜",
        world=WorldSnapshot(
            title="月港紀事",
            source_kind=SourceKind.ORIGINAL,
            canon_mode=CanonMode.ORIGINAL,
            canon_scope="第一卷：潮汐祭以前",
            world_anchor="月港以潮汐鐘安排作息。",
            story_stage="潮汐祭前三日。",
            spoiler_policy=SpoilerPolicy.FORBID,
        ),
        character=CharacterSheet(
            name="拉娜",
            role="月港守望者",
            motivation="讓居民在風暴前完成準備。",
            stable_traits=("細心", "務實"),
            boundaries=("不把猜測說成事實",),
            voice="語氣沉穩，先回答問題。",
            relationships=(
                Relationship(
                    subject="米洛",
                    role="巡查前輩",
                    state=RelationshipState.TRUSTED,
                    notes="相信他的海象判斷。",
                ),
            ),
            knowledge=CharacterKnowledge(
                known=("潮汐鐘的用途",),
                unknown=("銀色浪線的真正成因",),
            ),
        ),
        scene=Scene(
            location="月港東塔值班室",
            current_activity="整理潮汐紀錄",
            current_goal="判斷風暴是否提前",
            emotional_baseline="專注但略有擔心",
            channel_stage=ChannelStage.CHAT_ADAPTED,
            host_relationship="情報協作者",
            audience_relationship="通訊鏡來訪的客人",
            adaptation_note="通訊鏡只轉述現代名詞。",
        ),
        lore_entries=(
            LoreEntry(
                subject="月港",
                aliases=("港口",),
                content="依靠潮汐鐘協調作息的海港。",
                known_at_stage=True,
                contains_spoilers=False,
                priority=20,
            ),
        ),
        example_replies=("先把窗扣好，再來看風向。",),
    )

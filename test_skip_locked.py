"""Test FOR UPDATE SKIP LOCKED behavior with SQLite."""
import asyncio
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy import Column, String, DateTime, Integer, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

Base = declarative_base()


class MeetingReminder(Base):
    __tablename__ = "meeting_reminders"
    id = Column(String, primary_key=True)
    meeting_id = Column(String)
    reminder_type = Column(String)
    scheduled_for = Column(DateTime(timezone=True))
    status = Column(String)
    idempotency_key = Column(String)
    schedule_generation = Column(Integer)


async def test_skip_locked():
    engine = create_async_engine("sqlite:///:memory:", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Create a test reminder
        reminder = MeetingReminder(
            id="test-1",
            meeting_id="test-meeting",
            reminder_type="24h",
            scheduled_for=f"{func.now() + 86400}",  # tomorrow
            status="pending",
            idempotency_key="test-key-1",
            schedule_generation=1,
        )
        session.add(reminder)
        await session.commit()
        await session.refresh(reminder)
        
        # Try to claim with skip_locked
        from app.services.meeting_service import MeetingService
        
        # First claim
        claimed1 = await service.claim_due_reminders(limit=1)
        print(f"First claim: {len(claimed1)} reminders, status={claimed1[0].status if claimed1 else 'none'}")
        
        # Second claim - should get 0 if skip_locked works
        claimed2 = await service.claim_due_reminders(limit=1)
        print(f"Second claim: {len(claimed2)} reminders")


service = None

async def main():
    global service
    service = MeetingService()
    await test_skip_locked()

asyncio.run(main())
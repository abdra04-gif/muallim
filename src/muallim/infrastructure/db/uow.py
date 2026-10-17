from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from muallim.application.ports.repositories import UnitOfWork


@dataclass(frozen=True, slots=True)
class SqlUnitOfWork(UnitOfWork):
    session: AsyncSession

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

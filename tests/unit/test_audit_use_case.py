from uuid import uuid4

from tests.fakes import FakeUoW
from woassi.shared.application.audit import ListAuditEntries


async def test_lists_a_page_of_one_shop_only() -> None:
    uow = FakeUoW()
    shop_id = uuid4()
    for number in range(3):
        await uow.audit.record(
            account_id=uuid4(),
            action="order.validated",
            target_type="order",
            target_id=str(number),
            shop_id=shop_id,
        )
    await uow.audit.record(
        account_id=uuid4(), action="x", target_type="y", target_id="z", shop_id=uuid4()
    )

    page = await ListAuditEntries(uow).execute(shop_id=shop_id, offset=1, limit=1)

    assert [entry.target_id for entry in page.items] == ["1"]
    assert (page.total, page.offset, page.limit) == (3, 1, 1)

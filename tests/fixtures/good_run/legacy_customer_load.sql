-- SYNTHETIC EXAMPLE: simplified legacy load used only as test fixture
-- R1: status mapping
SELECT c.CUSTOMER_ID,
       CASE c.STATUS WHEN 'A' THEN 'ACTIVE' WHEN 'S' THEN 'SUSPENDED' ELSE 'ARCHIVED' END AS STATUS_NEW,
       c.EMAIL
  FROM CUSTOMER c
 WHERE c.DELETED_FLAG <> 'Y'                       -- R2: soft-deleted customers are not migrated
   AND c.CREATED_AT = (SELECT MAX(x.CREATED_AT)    -- R3: duplicates on EMAIL keep the latest record
                         FROM CUSTOMER x WHERE x.EMAIL = c.EMAIL);
-- R4: orders loaded more than 2 days after ORDER_DATE are reprocessed as late-arriving
-- R5: TOTAL_EUR = 0 goes to manual review, TOTAL_EUR > 10000 needs a second approval
-- R6: customers without EMAIL receive a generated placeholder address

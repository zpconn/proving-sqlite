u8 contract_sqlite3VdbeOneByteSerialTypeLen(u8 serial_type)
  __CPROVER_requires(serial_type < 128)
  __CPROVER_assigns()
  __CPROVER_ensures(__CPROVER_return_value <= 255);

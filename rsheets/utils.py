from enum import Enum
import time
from typing import Any, Callable

import gspread

class ExpandingTable:
    
    table: list[list[str]]
    
    num_cols: int
    changed: set[tuple[int, int]]
        
    @property
    def num_rows(self) -> int:
        return len(self.table)
    
    def __init__(self) -> None:
        self.clear()
        self.reset_changed()
        
    def __str__(self) -> str:
        return '[' + ',\n '.join(str(row) for row in self.table) + ']'
    
    def add_row(self, row: list[Any]) -> None:
        self.table.append([]) # eeeehhhhh
        self.set_row(len(self.table) - 1, row)
    
    def add_rows(self, rows: list[list[Any]]) -> None:
        for row in rows:
            self.add_row(row)
            
    def set_row(self, index: int, row: list[Any]) -> None:
        str_row = [str(element) for element in row]
        new_num_cols = len(str_row)
        if new_num_cols > self.num_cols:
            self.extend_columns(new_num_cols)
            self.table[index] = str_row
        elif new_num_cols < self.num_cols:
            self.table[index] = str_row + [''] * (self.num_cols - new_num_cols)
        else:
            self.table[index] = str_row
        for c in range(len(self.table[index])):
            self.changed.add((index, c))
            
    def set_cell(self, row: int, col: int, value: Any) -> None:
        self.table[row][col] = str(value)
        self.changed.add((row, col))
        
    def get_cell(self, row: int, col: int, sheet_format: bool = False) -> str:
        if row < self.num_rows and col < self.num_cols:
            return prepend_quote(self.table[row][col]) if sheet_format else self.table[row][col]
        return ''
    
    def export(self) -> list[list[str]]:
        return [[prepend_quote(value) for value in row] for row in self.table]
        
    def clear(self) -> None:
        self.table = []
        self.num_cols = 0
        for row in range(len(self.table)):
            for col in range(len(row)):
                self.changed.add((row, col))
    
    def reset_changed(self) -> None:
        self.changed = set()
        
    def get_changed_rect(self) -> tuple[tuple[int, int], tuple[int, int]]:
        if len(self.changed) == 0:
            return None
        min_row: int | None = None; max_row: int | None = None
        min_col: int | None = None; max_col: int | None = None
        for cell in self.changed:
            if min_row is None:
                min_row = max_row = cell[0]
                min_col = max_col = cell[1]
            else:
                if cell[0] < min_row:
                    min_row = cell[0]
                elif cell[0] > max_row:
                    max_row = cell[0]
                if cell[1] < min_col:
                    min_col = cell[1]
                elif cell[1] > max_col:
                    max_col = cell[1]
        return ((min_row, max_row), (min_col, max_col))
        
    def rebuild(self, new_table: list[list[Any]]) -> None:
        self.clear()
        self.add_rows(new_table)
            
    def initialize(self, num_rows: int, num_cols: int) -> None:
        self.clear()
        self.table = [['' for c in num_cols] for r in num_rows]
            
    def extend_columns(self, new_size: int) -> None:
        for row_index, row in enumerate(self.table):
            row.extend([''] * (new_size - self.num_cols))
            for new_col in range(new_size - self.num_cols):
                self.changed.add((self.num_cols + new_col, row_index))
        self.num_cols = new_size
        

def safe_request(func: Callable, *args) -> Any:
    """Call a function, timing out on request limit issues.

    :param func: The function to call with the supplied parameters.
    :type func: Callable
    :return: The result of the function call if successful, else None.
    :rtype: Any
    """
    try:
        return func(*args)
    except gspread.exceptions.APIError:
        print("Limit of 100 requests per 100 seconds exceeded. Activating cooldown...")
        time.sleep(100) # wait until sure that request limit is reset
        try:
            return func(*args) # try again
        except gspread.exceptions.APIError:
            print("Still recieving error, may not be request limit related. Giving up...")

def prepad_columns(array2d: list[list[str]], num_cols: int, replace: bool = False):
    if replace:
        for row in array2d:
            for col in range(num_cols):
                row[col] = ''
    else:
        for i, row in enumerate(array2d):
            array2d[i] = [''] * num_cols + row
    return array2d

def prepend_quote(value: str) -> str:
    # prepends ' characters to define them as strings on Google Sheets (except formulas)
    return value if value == '' or value.startswith('=') else f'\'{value}'

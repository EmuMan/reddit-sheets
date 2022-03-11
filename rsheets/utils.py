from enum import Enum
import time
from typing import Any, Callable

import gspread

class ExpandingTable:
    
    table: list[list[str]]
    
    num_cols: int
        
    @property
    def num_rows(self) -> int:
        return len(self.table)
    
    def __init__(self) -> None:
        self.clear()
        
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
            
    def set_cell(self, row: int, col: int, value: Any) -> None:
        self.table[row][col] = str(value)
        
    def get_cell(self, row: int, col: int) -> str:
        if row < self.num_rows and col < self.num_cols: return self.table[row][col]
        return ''
        
    def clear(self) -> None:
        self.table = []
        self.num_cols = 0
        
    def rebuild(self, new_table: list[list[Any]]) -> None:
        self.clear()
        self.add_rows(new_table)
            
    def initialize(self, num_rows: int, num_cols: int) -> None:
        self.clear()
        self.table = [['' for c in num_cols] for r in num_rows]
            
    def extend_columns(self, new_size: int) -> None:
        for row in self.table:
            row.extend([''] * (new_size - self.num_cols))
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

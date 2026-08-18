import functools


@functools.total_ordering
class FruitItem:

    def __init__(self, fruit, amount):
        self.fruit = fruit
        self.amount = amount

    def __add__(self, other):
        return FruitItem(self.fruit, self.amount + other.amount)

    def __eq__(self, other):
        return self.fruit == other.fruit and self.amount == other.amount

    def __lt__(self, other):
        if self.amount == other.amount:
            return self.fruit < other.fruit
        return self.amount < other.amount

    def __str__(self):
        return f"{self.fruit:16} {self.amount:5d}"

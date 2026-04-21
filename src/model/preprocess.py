import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class DatePreprocessor(BaseEstimator, TransformerMixin):
    def __init__(self, col: str):
        self.col = col

    def fit(self, X, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X):
        X = X.copy()
        X[self.col] = pd.to_datetime(X[self.col])
        X = X.sort_values(by=self.col)
        date_range = pd.date_range(start=X[self.col].min(), end=X[self.col].max(), freq="h")
        date_frame = pd.DataFrame(date_range, columns=[self.col])
        return pd.merge(date_frame, X, on=self.col, how="left")


class SlidingWindowTransformer(BaseEstimator, TransformerMixin):
    def __init__(self, window_size: int):
        self.window_size = window_size

    def fit(self, X, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X):
        return self.create_sliding_windows(np.asarray(X), self.window_size)

    @staticmethod
    def create_sliding_windows(data: np.ndarray, window_size: int):
        X_transformed, y_transformed = [], []
        for index in range(len(data) - window_size):
            X_transformed.append(data[index : index + window_size])
            y_transformed.append(data[index + window_size])
        return np.array(X_transformed), np.array(y_transformed)

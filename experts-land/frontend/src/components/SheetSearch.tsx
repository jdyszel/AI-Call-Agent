import React, { useState } from 'react';
import {
  Box,
  Button,
  Typography,
  CircularProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import axios from 'axios';

interface SheetFile {
  name: string;
  created: string;
}

interface SearchResponse {
  total_sheets: number;
  oldest_created: string | null;
  newest_modified: string | null;
  files: SheetFile[];
}

const SheetSearch: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get<SearchResponse>('/api/sheet-search');
      setSearchResults(response.data);
    } catch (err) {
      setError('Failed to fetch sheet data. Please try again.');
      console.error('Error fetching sheets:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        Google Sheets Archive Search
      </Typography>

      <Button
        variant="contained"
        onClick={handleSearch}
        disabled={loading}
        sx={{ mb: 3 }}
      >
        Run Sheets Search
      </Button>

      {loading && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <CircularProgress size={24} />
          <Typography>Scanning in progress...</Typography>
        </Box>
      )}

      {error && (
        <Typography color="error" sx={{ mb: 3 }}>
          {error}
        </Typography>
      )}

      {searchResults && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            ✅ Scan complete: We found {searchResults.total_sheets} survey files.
          </Typography>
          <Typography paragraph>
            Oldest file created on {formatDate(searchResults.oldest_created)}.
          </Typography>
          <Typography paragraph>
            Most recently modified file on {formatDate(searchResults.newest_modified)}.
          </Typography>

          {searchResults.files.length > 0 && (
            <TableContainer component={Paper}>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>File Name</TableCell>
                    <TableCell>Creation Date</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {searchResults.files.map((file, index) => (
                    <TableRow key={index}>
                      <TableCell>{file.name}</TableCell>
                      <TableCell>{formatDate(file.created)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Paper>
      )}
    </Box>
  );
};

export default SheetSearch; 